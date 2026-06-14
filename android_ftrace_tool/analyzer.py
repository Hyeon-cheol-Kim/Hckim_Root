"""
Android ftrace 로그 사후 분석 (correlation analyzer)
====================================================
캡처한 .log 를 파싱해, 계층을 관통하는 "조인 키"로 이벤트들을 연결한다.

조인 키(왜 이걸로 연결되는가):
  - block ↔ scsi ↔ ufs : sector / LBA   (device sector = LBA × (논리블록/512))
  - 파일 ↔ 블록          : f2fs_map_blocks 의 m_pblk(파일 물리블록) + 파티션 오프셋
  - 앱 ↔ 파일            : inode(ino) + 파일 오프셋(=논리블록)

한계(로그만으로 100% 인과 보장 불가):
  - read 캐시 히트는 하위 명령이 없고, readahead/병합으로 1:N·N:1 발생
  - write 는 writeback 스레드가 나중에 flush → 앱과 다른 컨텍스트/시각
  따라서 아래 결과의 "파일 추정" 은 시간·키 기반 best-effort 매칭이다.

사용법:
  python -m android_ftrace_tool.analyzer <capture.log> [-o report.txt]
                                         [--lbs 4096] [--limit 50]
"""

import re
import sys
import argparse
from collections import defaultdict, Counter


# ── 공통 라인 파서 ─────────────────────────────────────────────────
# 예) "  app_process64-4821  [002] ...1  2207.114502: event_name: rest..."
_LINE_RE = re.compile(
    r'^\s*(?P<task>.+?)-(?P<pid>\d+)\s+\[(?P<cpu>\d+)\]\s+'
    r'(?P<flags>\S+)\s+(?P<ts>\d+\.\d+):\s+(?P<event>[\w]+):\s?(?P<rest>.*)$'
)

# block_rq_issue/complete/bio_queue: "254,52 WS [bytes] [()] <sector> + <nr> [comm]"
_BLOCK_RE = re.compile(
    r'(?P<maj>\d+),(?P<min>\d+)\s+(?P<rwbs>[A-Za-z]+)\s+'
    r'(?:\d+\s+)?(?:\(.*?\)\s+)?(?P<sector>\d+)\s+\+\s+(?P<nr>\d+)'
)
# ufshcd_command rest
_UFS_STR_RE = re.compile(r'^(?P<str>\w+):')
_UFS_TAG_RE = re.compile(r'tag:\s*(\d+)')
_UFS_LBA_RE = re.compile(r'LBA:\s*(\d+)')
_UFS_SIZE_RE = re.compile(r'size:\s*(\d+)')
_UFS_OP_RE = re.compile(r'opcode:\s*0x([0-9a-fA-F]+)\s*\((\w+)\)')
# scsi cmnd
_SCSI_NAME_RE = re.compile(r'cmnd=\((\w+)')
_SCSI_LBA_RE = re.compile(r'lba=(\d+)')
# f2fs_map_blocks (필드명은 커널마다 달라 개별 추출)
_INO_RE = re.compile(r'ino\s*=?\s*(\d+)')
_PBLK_RE = re.compile(r'm_pblk\s*=\s*(\d+)')
_LBLK_RE = re.compile(r'm_lblk\s*=\s*(\d+)')
_MLEN_RE = re.compile(r'm_len\s*=\s*(\d+)')
# android_fs
_AFS_INO_RE = re.compile(r'\bino\s+(\d+)')
_AFS_PATH_RE = re.compile(r'pathbase\s+(\S+)')
_AFS_BYTES_RE = re.compile(r'bytes\s+(\d+)')
_AFS_OFF_RE = re.compile(r'offset\s+(\d+)')
# io_latency 합성 이벤트
_SYN_LAT_RE = re.compile(r'lat=(\d+)')
_SYN_SECTOR_RE = re.compile(r'sector=(\d+)')


class Parsed:
    """파싱 결과 컨테이너."""
    def __init__(self):
        self.total = 0
        self.matched = 0
        self.ufs = []          # {ts,str,tag,lba,size,op,opname,cpu}
        self.block_issue = []  # {ts,dev,sector,nr,rwbs,comm}
        self.block_complete = []
        self.scsi = []         # {ts,name,lba}
        self.f2fs_map = []     # {ts,ino,pblk,lblk,mlen}
        self.android_fs = []   # {ts,ino,path,bytes,offset,op,pid,task}
        self.io_latency = []   # {ts,sector,lat}


def parse_log(path):
    """로그 파일을 읽어 Parsed 로 반환."""
    p = Parsed()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            p.total += 1
            m = _LINE_RE.match(line)
            if not m:
                continue
            ev = m.group("event")
            rest = m.group("rest")
            ts = float(m.group("ts"))
            try:
                _dispatch(p, ev, rest, ts, m)
            except Exception:
                # 형식이 예상과 달라도 분석 전체가 멈추지 않게 한다.
                continue
    return p


def _dispatch(p, ev, rest, ts, m):
    if ev == "ufshcd_command":
        sm = _UFS_STR_RE.match(rest)
        op = _UFS_OP_RE.search(rest)
        tag = _UFS_TAG_RE.search(rest)
        lba = _UFS_LBA_RE.search(rest)
        size = _UFS_SIZE_RE.search(rest)
        p.ufs.append({
            "ts": ts, "str": sm.group("str") if sm else "",
            "tag": int(tag.group(1)) if tag else None,
            "lba": int(lba.group(1)) if lba else None,
            "size": int(size.group(1)) if size else None,
            "op": op.group(1) if op else None,
            "opname": op.group(2) if op else None,
            "cpu": m.group("cpu"),
        })
        p.matched += 1
    elif ev in ("block_rq_issue", "block_rq_complete", "block_bio_queue"):
        bm = _BLOCK_RE.search(rest)
        if not bm:
            return
        comm = rest.rsplit("[", 1)[-1].rstrip("]\n ") if "[" in rest else ""
        rec = {"ts": ts, "dev": f"{bm.group('maj')},{bm.group('min')}",
               "sector": int(bm.group("sector")), "nr": int(bm.group("nr")),
               "rwbs": bm.group("rwbs"), "comm": comm}
        if ev == "block_rq_complete":
            p.block_complete.append(rec)
        elif ev == "block_rq_issue":
            p.block_issue.append(rec)
        p.matched += 1
    elif ev in ("scsi_dispatch_cmd_start", "scsi_dispatch_cmd_done"):
        name = _SCSI_NAME_RE.search(rest)
        lba = _SCSI_LBA_RE.search(rest)
        p.scsi.append({"ts": ts, "name": name.group(1) if name else None,
                       "lba": int(lba.group(1)) if lba else None})
        p.matched += 1
    elif ev == "f2fs_map_blocks":
        ino = _INO_RE.search(rest)
        pblk = _PBLK_RE.search(rest)
        lblk = _LBLK_RE.search(rest)
        mlen = _MLEN_RE.search(rest)
        p.f2fs_map.append({"ts": ts,
                           "ino": int(ino.group(1)) if ino else None,
                           "pblk": int(pblk.group(1)) if pblk else None,
                           "lblk": int(lblk.group(1)) if lblk else None,
                           "mlen": int(mlen.group(1)) if mlen else None})
        p.matched += 1
    elif ev.startswith("android_fs_dataread") or ev.startswith("android_fs_datawrite"):
        ino = _AFS_INO_RE.search(rest)
        path = _AFS_PATH_RE.search(rest)
        bytes_ = _AFS_BYTES_RE.search(rest)
        off = _AFS_OFF_RE.search(rest)
        p.android_fs.append({"ts": ts,
                             "ino": int(ino.group(1)) if ino else None,
                             "path": path.group(1) if path else "?",
                             "bytes": int(bytes_.group(1)) if bytes_ else None,
                             "offset": int(off.group(1)) if off else None,
                             "op": "read" if "read" in ev else "write",
                             "pid": m.group("pid"), "task": m.group("task")})
        p.matched += 1
    elif ev == "io_latency":   # 합성 이벤트(상관 트리거 결과)
        lat = _SYN_LAT_RE.search(rest)
        sec = _SYN_SECTOR_RE.search(rest)
        if lat and sec:
            p.io_latency.append({"ts": ts, "lat": int(lat.group(1)),
                                 "sector": int(sec.group(1))})
            p.matched += 1


# ── 상관(연결) 계산 ────────────────────────────────────────────────
def _detect_ratio(p):
    """device sector = LBA × ratio 의 ratio 를 후보 중 매칭이 가장 많은 값으로 추정."""
    sectors = {b["sector"] for b in p.block_issue}
    lbas = [u["lba"] for u in p.ufs if u["lba"] is not None]
    if not sectors or not lbas:
        return 8           # 일반적 4K 논리블록 기본값
    best_r, best_hits = 8, -1
    for r in (8, 16, 4, 2, 1):
        hits = sum(1 for lba in lbas if lba * r in sectors)
        if hits > best_hits:
            best_r, best_hits = r, hits
    return best_r


def _ufs_latencies(p):
    """ufshcd_command send→complete 를 tag(FIFO)로 묶어 device 지연(us) 산출."""
    pending = defaultdict(list)   # tag -> [send 레코드,...]
    out = []
    for u in sorted(p.ufs, key=lambda x: x["ts"]):
        if u["str"] == "send":
            pending[u["tag"]].append(u)
        elif u["str"] in ("complete", "dev_complete"):
            q = pending.get(u["tag"])
            if q:
                s = q.pop(0)
                out.append({**u, "lat_us": (u["ts"] - s["ts"]) * 1e6,
                            "lba": u["lba"] if u["lba"] is not None else s["lba"],
                            "opname": u["opname"] or s["opname"]})
    return out


def _block_latencies(p):
    """block_rq_issue→complete 를 (dev,sector)로 묶어 블록 지연(us) 산출."""
    # io_latency 합성 이벤트가 있으면 그것을 우선 사용(커널 조인 결과).
    syn = {s["sector"]: s["lat"] for s in p.io_latency}
    pending = defaultdict(list)
    out = {}
    for b in sorted(p.block_issue, key=lambda x: x["ts"]):
        pending[(b["dev"], b["sector"])].append(b)
    for c in sorted(p.block_complete, key=lambda x: x["ts"]):
        q = pending.get((c["dev"], c["sector"]))
        if q:
            s = q.pop(0)
            lat = syn.get(c["sector"], (c["ts"] - s["ts"]) * 1e6)
            out[c["sector"]] = {"lat_us": lat, "comm": s["comm"],
                                "rwbs": s["rwbs"], "nr": s["nr"]}
    # 완료가 없어도 issue 정보는 보존
    for b in p.block_issue:
        out.setdefault(b["sector"], {"lat_us": None, "comm": b["comm"],
                                     "rwbs": b["rwbs"], "nr": b["nr"]})
    return out


def _infer_partition_offset(p, ratio, window=0.05):
    """
    block.sector 와 f2fs_map.m_pblk 의 관계: sector = part_offset + pblk×ratio.
    시간상 가까운 (f2fs_map, block_issue) 쌍에서 offset 후보를 모아 최빈값을 택한다.
    """
    if not p.f2fs_map or not p.block_issue:
        return None
    cands = Counter()
    blocks = sorted(p.block_issue, key=lambda x: x["ts"])
    for fm in p.f2fs_map:
        if fm["pblk"] is None:
            continue
        for b in blocks:
            if abs(b["ts"] - fm["ts"]) > window:
                continue
            off = b["sector"] - fm["pblk"] * ratio
            if off >= 0:
                cands[off] += 1
    if not cands:
        return None
    return cands.most_common(1)[0][0]


def _ino_to_file(p):
    """ino → (path, op) 매핑(android_fs 기준, 가장 최근 것)."""
    table = {}
    for a in p.android_fs:
        if a["ino"] is not None:
            table[a["ino"]] = (a["path"], a["op"])
    return table


def correlate(p):
    """파싱 결과로부터 UFS 명령 중심의 상관 체인을 만든다."""
    ratio = _detect_ratio(p)
    ufs_lat = _ufs_latencies(p)
    blk = _block_latencies(p)
    part_off = _infer_partition_offset(p, ratio)
    ino_file = _ino_to_file(p)
    # pblk → ino (f2fs_map)
    pblk_ino = {fm["pblk"]: fm["ino"] for fm in p.f2fs_map if fm["pblk"] is not None}

    chains = []
    for u in ufs_lat:
        lba = u["lba"]
        chain = {"ufs": u, "block": None, "file": None}
        if lba is not None:
            sector = lba * ratio
            chain["block"] = blk.get(sector)
            # 파일 추정: sector → f2fs pblk → ino → path
            if part_off is not None:
                pblk = (sector - part_off) // ratio
                ino = pblk_ino.get(pblk)
                if ino is not None and ino in ino_file:
                    path, op = ino_file[ino]
                    chain["file"] = {"ino": ino, "path": path, "op": op}
        chains.append(chain)
    return {"ratio": ratio, "part_off": part_off, "chains": chains,
            "ufs_lat": ufs_lat, "blk": blk}


# ── 리포트 ─────────────────────────────────────────────────────────
def _opclass(name):
    if not name:
        return "OTHER"
    n = name.upper()
    if "READ" in n:
        return "READ"
    if "WRITE" in n:
        return "WRITE"
    if "UNMAP" in n or "DISCARD" in n:
        return "DISCARD/ERASE"
    if "SYNC" in n:
        return "SYNC(flush)"
    return "OTHER"


def build_report(p, corr, limit=50):
    L = []
    A = L.append
    A("=" * 70)
    A(" Android ftrace 상관 분석 리포트")
    A("=" * 70)
    A(f" 파싱 라인: {p.total}  (인식 이벤트: {p.matched})")
    A(f" 이벤트 수 — ufs:{len(p.ufs)} block_issue:{len(p.block_issue)} "
      f"scsi:{len(p.scsi)} f2fs_map:{len(p.f2fs_map)} android_fs:{len(p.android_fs)} "
      f"io_latency:{len(p.io_latency)}")
    A(f" sector=LBA×{corr['ratio']} 로 추정, 파티션 오프셋(sector) 추정: {corr['part_off']}")
    if not corr["ufs_lat"]:
        A("")
        A(" [안내] ufshcd_command(send/complete) 가 없어 UFS 상관을 만들 수 없습니다.")
        A("        'ufs' 그룹(또는 f 프리셋)을 켜고 다시 캡처하세요.")
        return "\n".join(L)

    # 요약 통계
    by_class = defaultdict(list)
    for u in corr["ufs_lat"]:
        by_class[_opclass(u["opname"])].append(u["lat_us"])
    A("")
    A(" ── UFS 명령 요약 (opcode 분류별 device 지연) ──")
    A(f"   {'분류':<14}{'건수':>6}{'평균us':>10}{'최대us':>10}")
    for cls, lats in sorted(by_class.items()):
        lats2 = [x for x in lats if x is not None]
        avg = sum(lats2) / len(lats2) if lats2 else 0
        mx = max(lats2) if lats2 else 0
        A(f"   {cls:<14}{len(lats):>6}{avg:>10.1f}{mx:>10.1f}")

    # 상관 체인 (앞에서 limit 개)
    matched_file = sum(1 for c in corr["chains"] if c["file"])
    matched_block = sum(1 for c in corr["chains"] if c["block"])
    A("")
    A(f" ── 상관 체인 (UFS↔block↔파일, 상위 {min(limit, len(corr['chains']))}건) ──")
    A(f"   (block 매칭 {matched_block}/{len(corr['chains'])}, "
      f"파일 추정 {matched_file}/{len(corr['chains'])})")
    for c in corr["chains"][:limit]:
        u = c["ufs"]
        line = (f"   [UFS {(u['opname'] or '?'):<11} LBA={u['lba']} "
                f"tag={u['tag']} dev_lat={u['lat_us']:.1f}us]")
        A(line)
        if c["block"]:
            b = c["block"]
            bl = f"{b['lat_us']:.1f}us" if b["lat_us"] is not None else "?"
            A(f"        ↔ block sector={u['lba'] * corr['ratio']} rwbs={b['rwbs']} "
              f"nr={b['nr']} blk_lat={bl} comm={b['comm']}")
        if c["file"]:
            fobj = c["file"]
            A(f"        ↔ 파일(추정) ino={fobj['ino']} path={fobj['path']} op={fobj['op']}")
    A("")
    A(" ※ '파일(추정)' 은 sector→f2fs pblk→ino→path 의 best-effort 매칭입니다.")
    A("   캐시 히트/리드어헤드/병합/비동기 writeback 때문에 1:1 보장은 아닙니다.")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Android ftrace 로그 상관 분석기")
    ap.add_argument("logfile", help="분석할 캡처 .log 파일")
    ap.add_argument("-o", "--output", help="리포트를 저장할 파일(미지정 시 화면 출력)")
    ap.add_argument("--limit", type=int, default=50, help="상관 체인 출력 개수(기본 50)")
    args = ap.parse_args(argv)

    try:
        p = parse_log(args.logfile)
    except OSError as e:
        print(f"[오류] 로그 파일을 열 수 없습니다: {e}")
        return 1

    corr = correlate(p)
    report = build_report(p, corr, limit=args.limit)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(report + "\n")
            print(f"리포트 저장: {args.output}")
        except OSError as e:
            print(f"[오류] 리포트 저장 실패: {e}")
            return 1
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
