"""
bpftrace 스크립트 생성기 (커널-내 상관, in-kernel correlation)
================================================================
ftrace 로그는 "이벤트 나열 + 사후 매칭"이라 1:1 인과 보장이 어렵다(analyzer.py
참고). bpftrace 는 eBPF 로 **커널 안에서** 조인 키(sector/tag/tid)별 맵을 잡아
지연을 그 자리에서 계산하므로, 로그 후처리 없이 진짜 1:1 상관과 정확한 지연을
얻는다. 이 모듈은 스토리지 I/O 경로용 bpftrace 스크립트를 만들어 준다.

전제(디바이스):
  - 루팅(su) 또는 adb root 가능 + eBPF/ BTF 지원 커널
  - 디바이스에 bpftrace 바이너리(보통 /data/local/tmp/bpftrace 로 push)

주의: ufs/f2fs tracepoint 의 인자 이름은 커널 버전마다 다를 수 있다. 스크립트
상단 주석의 "필드 확인" 안내대로 format 을 확인해 args.* 이름을 맞추면 된다.

사용법:
  python -m android_ftrace_tool.bpftrace list
  python -m android_ftrace_tool.bpftrace show block_latency
  python -m android_ftrace_tool.bpftrace save block_latency -o biolat.bt
  python -m android_ftrace_tool.bpftrace run  block_latency \
        --bpftrace /data/local/tmp/bpftrace --duration 10 [-s SERIAL]
"""

import os
import sys
import tempfile
import argparse


# ── 스크립트 템플릿 ────────────────────────────────────────────────
# 각 스크립트는 조인 키로 맵을 잡아 지연을 커널 안에서 계산한다.
BPF_SCRIPTS = {
    # block_rq_issue ↔ complete 를 (dev,sector)로 조인 → 제출 프로세스별 지연
    "block_latency": {
        "desc": "블록 I/O 지연을 (dev,sector)로 조인, 제출 comm·rwbs별 히스토그램",
        "script": r"""// block_latency.bt — 블록계층 왕복 지연(제출 프로세스 기준)
// 조인 키: (dev, sector). issue 시점의 comm 을 보존해 진짜 제출자에 귀속.
BEGIN { printf("blk latency by comm/rwbs. Ctrl-C to print.\n"); }

tracepoint:block:block_rq_issue
{
    @s[args.dev, args.sector] = nsecs;
    @c[args.dev, args.sector] = comm;
    @rw[args.dev, args.sector] = args.rwbs;
}
tracepoint:block:block_rq_complete
/ @s[args.dev, args.sector] /
{
    $us = (nsecs - @s[args.dev, args.sector]) / 1000;
    @lat_us[@c[args.dev, args.sector], @rw[args.dev, args.sector]] = hist($us);
    delete(@s[args.dev, args.sector]);
    delete(@c[args.dev, args.sector]);
    delete(@rw[args.dev, args.sector]);
}
END { clear(@s); clear(@c); clear(@rw); }
""",
    },

    # ufshcd_command send ↔ complete 를 tag 로 조인 → opcode별 device 지연
    "ufs_latency": {
        "desc": "UFS device 지연을 tag로 조인(send↔complete), opcode별 히스토그램",
        "script": r"""// ufs_latency.bt — UFS 디바이스 처리 지연(send→complete)
// 조인 키: tag. str 필드로 send/complete 구분.
// [필드 확인] adb shell cat /sys/kernel/tracing/events/ufs/ufshcd_command/format
//   → args.str / args.tag / args.opcode 이름이 다르면 아래를 맞추세요.
BEGIN { printf("UFS device latency by opcode. Ctrl-C to print.\n"); }

tracepoint:ufs:ufshcd_command
/ str(args.str) == "send" /
{
    @u[args.tag] = nsecs;
    @op[args.tag] = args.opcode;
}
tracepoint:ufs:ufshcd_command
/ str(args.str) == "complete" && @u[args.tag] /
{
    $us = (nsecs - @u[args.tag]) / 1000;
    @ufs_us[@op[args.tag]] = hist($us);
    delete(@u[args.tag]);
    delete(@op[args.tag]);
}
END { clear(@u); clear(@op); }
""",
    },

    # vfs_read/write 왕복 지연 → 동기 경로를 프로세스별로
    "vfs_rw_latency": {
        "desc": "vfs_read/vfs_write 왕복 지연을 tid로 조인, 프로세스별 히스토그램",
        "script": r"""// vfs_rw_latency.bt — VFS read/write 동기 경로 지연(프로세스 기준)
// 조인 키: tid (커널 스레드 식별). 캐시 히트 포함 전체 read/write 비용.
BEGIN { printf("vfs read/write latency by comm. Ctrl-C to print.\n"); }

kprobe:vfs_read  { @rd[tid] = nsecs; }
kretprobe:vfs_read  / @rd[tid] / {
    @read_us[comm] = hist((nsecs - @rd[tid]) / 1000); delete(@rd[tid]);
}
kprobe:vfs_write { @wr[tid] = nsecs; }
kretprobe:vfs_write / @wr[tid] / {
    @write_us[comm] = hist((nsecs - @wr[tid]) / 1000); delete(@wr[tid]);
}
END { clear(@rd); clear(@wr); }
""",
    },

    # 한 read() 가 실제 디바이스까지 내려가는 end-to-end 인과(같은 tid 추적)
    "read_to_device": {
        "desc": "read() 진입→block 제출까지 같은 tid로 인과 추적(동기 read 한정)",
        "script": r"""// read_to_device.bt — read() 호출이 블록 제출로 이어지는 인과(동기 경로)
// 조인 키: 같은 tid 안에서 vfs_read 구간에 발생한 block_rq_issue 를 귀속.
// (비동기 readahead/writeback 은 다른 컨텍스트라 잡히지 않을 수 있음)
BEGIN { printf("read()->block submit. comm: count, bytes. Ctrl-C.\n"); }

kprobe:vfs_read  { @in_read[tid] = 1; }
kretprobe:vfs_read { delete(@in_read[tid]); }

tracepoint:block:block_rq_issue
/ @in_read[tid] /
{
    @reads[comm] = count();
    @read_sectors[comm] = sum(args.nr_sector);
}
END { clear(@in_read); }
""",
    },
}


def list_scripts():
    """이름:설명 목록 문자열."""
    out = ["사용 가능한 bpftrace 스크립트:"]
    for name, s in BPF_SCRIPTS.items():
        out.append(f"  {name:<16} {s['desc']}")
    return "\n".join(out)


def generate(name):
    """스크립트 본문 문자열을 반환(없으면 KeyError 메시지)."""
    if name not in BPF_SCRIPTS:
        raise KeyError(name)
    return BPF_SCRIPTS[name]["script"]


def save(name, path):
    """스크립트를 파일로 저장하고 경로 반환."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(generate(name))
    return path


def run_on_device(name, bpftrace_bin, duration=10, adb=None,
                  remote_dir="/data/local/tmp"):
    """
    스크립트를 디바이스로 push 하고 bpftrace 로 duration 초 실행한 뒤 출력 반환.
    adb 는 core.Adb 인스턴스(없으면 기본 생성). 루트 권한과 디바이스의 bpftrace
    바이너리가 필요하다.
    """
    if adb is None:
        try:
            from .core import Adb
        except ImportError:
            from core import Adb
        adb = Adb()
    # 로컬 임시파일로 만든 뒤 push
    tmp = tempfile.NamedTemporaryFile("w", suffix=".bt", delete=False,
                                      encoding="utf-8")
    try:
        tmp.write(generate(name))
        tmp.close()
        remote = f"{remote_dir}/{name}.bt"
        adb.push(tmp.name, remote)
        # -c 가 아닌 timeout 으로 종료(BEGIN/END 출력 보장). chmod 후 실행.
        adb.shell(f"chmod 755 {bpftrace_bin}", check=False)
        cmd = f"timeout {duration} {bpftrace_bin} {remote}"
        # bpftrace 실행은 시간이 걸리므로 duration + 여유
        return adb.shell(cmd, timeout=duration + 30, check=False)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="bpftrace 커널-내 상관 스크립트 생성기")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list", help="스크립트 목록")

    p_show = sub.add_parser("show", help="스크립트 본문 출력")
    p_show.add_argument("name")

    p_save = sub.add_parser("save", help="스크립트를 파일로 저장")
    p_save.add_argument("name")
    p_save.add_argument("-o", "--output", help="저장 경로(기본 <name>.bt)")

    p_run = sub.add_parser("run", help="디바이스에 push 후 실행")
    p_run.add_argument("name")
    p_run.add_argument("--bpftrace", required=True,
                       help="디바이스의 bpftrace 바이너리 경로")
    p_run.add_argument("--duration", type=int, default=10, help="실행 초(기본 10)")
    p_run.add_argument("-s", "--serial", help="대상 디바이스 시리얼")
    p_run.add_argument("--su", action="store_true", help="su -c 로 권한 우회")

    args = ap.parse_args(argv)

    if args.cmd == "list" or args.cmd is None:
        print(list_scripts())
        return 0

    if args.name not in BPF_SCRIPTS:
        print(f"[오류] 알 수 없는 스크립트: {args.name}\n")
        print(list_scripts())
        return 1

    if args.cmd == "show":
        print(generate(args.name))
        return 0

    if args.cmd == "save":
        out = args.output or f"{args.name}.bt"
        save(args.name, out)
        print(f"저장: {out}")
        return 0

    if args.cmd == "run":
        try:
            from .core import Adb, AdbError
        except ImportError:
            from core import Adb, AdbError
        adb = Adb(serial=args.serial, use_su=args.su)
        try:
            out = run_on_device(args.name, args.bpftrace,
                                duration=args.duration, adb=adb)
        except AdbError as e:
            print(f"[오류] 실행 실패: {e}")
            return 1
        print(out)
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
