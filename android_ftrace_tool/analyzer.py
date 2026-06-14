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
    """
    이벤트 종류(ev)에 따라 rest(이벤트 뒷부분 필드 문자열)를 파싱해 Parsed 의
    해당 리스트에 적재한다. 필드명/형식은 커널 버전마다 조금씩 달라, 각 정규식은
    있으면 뽑고 없으면 None 으로 둔다(부분 정보라도 최대한 보존).
    """
    if ev == "ufshcd_command":
        # UFS 한 줄에서 송/완(str), opcode(0x..+이름), tag, LBA, size 를 뽑는다.
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
        # "maj,min RWBS [bytes] [()] sector + nr [comm]" 에서 dev/sector/nr/rwbs 추출.
        bm = _BLOCK_RE.search(rest)
        if not bm:
            return
        # 제출 프로세스명은 줄 끝 대괄호 [comm] 안에 있다(완료줄은 [0]일 수 있음).
        comm = rest.rsplit("[", 1)[-1].rstrip("]\n ") if "[" in rest else ""
        rec = {"ts": ts, "dev": f"{bm.group('maj')},{bm.group('min')}",
               "sector": int(bm.group("sector")), "nr": int(bm.group("nr")),
               "rwbs": bm.group("rwbs"), "comm": comm}
        # 발행/완료를 따로 모아 두면 _block_latencies 에서 (dev,sector)로 짝짓는다.
        if ev == "block_rq_complete":
            p.block_complete.append(rec)
        elif ev == "block_rq_issue":
            p.block_issue.append(rec)
        # block_bio_queue 는 큐잉 시점 참고용이라 별도 저장하지 않는다.
        p.matched += 1
    elif ev in ("scsi_dispatch_cmd_start", "scsi_dispatch_cmd_done"):
        name = _SCSI_NAME_RE.search(rest)
        lba = _SCSI_LBA_RE.search(rest)
        p.scsi.append({"ts": ts, "name": name.group(1) if name else None,
                       "lba": int(lba.group(1)) if lba else None})
        p.matched += 1
    elif ev == "f2fs_map_blocks":
        # 파일↔디바이스를 잇는 핵심: inode 와 그 파일의 물리블록(m_pblk).
        # (논리블록 m_lblk = 파일 오프셋/4K, m_len = 매핑 길이)
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
        # 앱↔파일 매핑: inode 로 실제 경로(path)/오프셋/바이트/프로세스를 알 수 있다.
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
    elif ev == "io_latency":   # 합성 이벤트(흐름 추적 트리거 결과)
        lat = _SYN_LAT_RE.search(rest)
        sec = _SYN_SECTOR_RE.search(rest)
        if lat and sec:
            p.io_latency.append({"ts": ts, "lat": int(lat.group(1)),
                                 "sector": int(sec.group(1))})
            p.matched += 1


# ── 흐름 추적(연결) 계산 ──────────────────────────────────────────
def _detect_ratio(p):
    """
    device sector = LBA × ratio 의 ratio 를 데이터에서 추정한다.

    block 계층의 sector 는 512B 단위, UFS LBA 는 디바이스 논리블록(보통 4K) 단위라
    둘 사이에는 ratio = 논리블록/512 (4K이면 8) 라는 고정 배수가 있다. 그러나 단말
    마다 논리블록 크기가 다를 수 있으므로, 후보 배수들 중 "LBA×r 가 실제 sector
    집합에 들어맞는 횟수(hits)"가 가장 큰 값을 정답으로 고른다.
    """
    # block 발행 sector 들을 set 으로 모아 빠른 멤버십 검사(LBA×r ∈ sectors)에 쓴다.
    sectors = {b["sector"] for b in p.block_issue}
    lbas = [u["lba"] for u in p.ufs if u["lba"] is not None]
    if not sectors or not lbas:
        return 8           # 한쪽이라도 비면 추정 불가 → 가장 흔한 4K(=×8) 기본값
    best_r, best_hits = 8, -1
    # 흔한 배수 후보들(4K=8, 8K=16, 2K=4, 1K=2, 512=1). 매칭 수가 최대인 것을 채택.
    for r in (8, 16, 4, 2, 1):
        hits = sum(1 for lba in lbas if lba * r in sectors)
        if hits > best_hits:
            best_r, best_hits = r, hits
    return best_r


def _ufs_latencies(p):
    """
    ufshcd_command 의 send→complete 를 tag 로 짝지어 device 처리 지연(us)을 구한다.

    같은 tag 는 동시에 하나만 떠 있는 게 보통이지만, 재사용될 수 있으므로 tag 별로
    큐(FIFO)를 두고 send 를 쌓았다가 complete 가 오면 가장 오래된 send 와 매칭한다.
    이벤트는 시간순으로 처리해야 짝이 어긋나지 않으므로 ts 로 정렬한다.
    """
    pending = defaultdict(list)   # tag -> [아직 complete 안 된 send 레코드들]
    out = []
    for u in sorted(p.ufs, key=lambda x: x["ts"]):
        if u["str"] == "send":
            # 발행: 나중에 complete 와 짝지을 수 있도록 보관.
            pending[u["tag"]].append(u)
        elif u["str"] in ("complete", "dev_complete"):
            # 완료: 같은 tag 의 가장 먼저 발행된 send 를 꺼내 지연을 계산.
            q = pending.get(u["tag"])
            if q:
                s = q.pop(0)
                out.append({**u,
                            # 초 단위 ts 차이를 us 로 환산(×1e6).
                            "lat_us": (u["ts"] - s["ts"]) * 1e6,
                            # complete 줄에 LBA/opcode 가 비면 send 값으로 보완.
                            "lba": u["lba"] if u["lba"] is not None else s["lba"],
                            "opname": u["opname"] or s["opname"]})
    return out


def _block_latencies(p):
    """
    block_rq_issue→complete 를 (dev,sector)로 짝지어 블록계층 왕복 지연(us)을 구하고,
    sector → {지연, 제출 comm, rwbs, nr} 매핑을 돌려준다.

    제출 프로세스(comm)는 issue 시점에만 정확하므로(완료는 보통 IRQ/idle 컨텍스트)
    issue 쪽 comm 을 보존한다. (B) 흐름 추적 트리거의 io_latency 합성 이벤트가 캡처에
    있으면, 커널이 직접 계산한 그 값을 우선 사용한다.
    """
    # io_latency(합성 이벤트)가 있으면 sector→lat 로 우선 참조 테이블 구성.
    syn = {s["sector"]: s["lat"] for s in p.io_latency}
    pending = defaultdict(list)   # (dev,sector) -> [아직 complete 안 된 issue 들]
    out = {}
    # issue 를 시간순으로 (dev,sector) 큐에 쌓는다.
    for b in sorted(p.block_issue, key=lambda x: x["ts"]):
        pending[(b["dev"], b["sector"])].append(b)
    # complete 마다 같은 키의 가장 오래된 issue 와 매칭해 지연을 산출.
    for c in sorted(p.block_complete, key=lambda x: x["ts"]):
        q = pending.get((c["dev"], c["sector"]))
        if q:
            s = q.pop(0)
            # 합성 이벤트 값이 있으면 그걸, 없으면 ts 차이로 직접 계산.
            lat = syn.get(c["sector"], (c["ts"] - s["ts"]) * 1e6)
            out[c["sector"]] = {"lat_us": lat, "comm": s["comm"],
                                "rwbs": s["rwbs"], "nr": s["nr"]}
    # 완료 이벤트가 캡처에 안 잡힌 issue 도 정보(comm 등)는 남긴다(지연은 None).
    for b in p.block_issue:
        out.setdefault(b["sector"], {"lat_us": None, "comm": b["comm"],
                                     "rwbs": b["rwbs"], "nr": b["nr"]})
    return out


def _infer_partition_offset(p, ratio, window=0.05):
    """
    파일↔디바이스를 잇기 위한 파티션 오프셋(섹터)을 데이터에서 추정한다.

    f2fs_map_blocks 의 m_pblk 는 '파티션 내부' 물리블록이고, block 계층 sector 는
    '디스크 절대' 섹터라, 둘 사이엔 sector = part_offset + pblk×ratio 의 고정
    오프셋이 있다(파티션 시작 위치). 이 오프셋을 모르면 파일을 디바이스 명령에 연결할
    수 없다. 그래서 시간상 가까운(window 초 이내) (f2fs_map, block_issue) 쌍마다
    오프셋 후보(sector − pblk×ratio)를 모으고, 가장 자주 나온 값(최빈값)을 택한다.
    오프셋은 상수이므로 진짜 값이 가장 많이 반복되어 노이즈를 이긴다.
    """
    if not p.f2fs_map or not p.block_issue:
        return None            # 한쪽이라도 없으면 다리(bridge)를 놓을 수 없음
    cands = Counter()          # 오프셋 후보 → 등장 횟수
    blocks = sorted(p.block_issue, key=lambda x: x["ts"])
    for fm in p.f2fs_map:
        if fm["pblk"] is None:
            continue
        for b in blocks:
            # 시간이 멀면 같은 I/O 일 가능성이 낮으므로 후보에서 제외.
            if abs(b["ts"] - fm["ts"]) > window:
                continue
            off = b["sector"] - fm["pblk"] * ratio
            if off >= 0:       # 음수 오프셋은 물리적으로 불가 → 무시
                cands[off] += 1
    if not cands:
        return None
    return cands.most_common(1)[0][0]   # 최빈 오프셋을 파티션 시작으로 채택


def _ino_to_file(p):
    """
    ino → (경로, op) 매핑을 만든다(android_fs 이벤트 기준).
    같은 ino 가 여러 번 나오면 뒤에 나온 것으로 덮어써 '가장 최근' 경로를 남긴다.
    """
    table = {}
    for a in p.android_fs:
        if a["ino"] is not None:
            table[a["ino"]] = (a["path"], a["op"])
    return table


def correlate(p):
    """
    파싱 결과(Parsed)로부터 'UFS 명령 1건 = 한 줄'인 흐름 추적 체인 목록을 만든다.

    각 체인은 UFS 명령을 기준으로:
      UFS(LBA) ──[sector=LBA×ratio]── block(sector) ──[+part_off, /ratio]──
      f2fs pblk ──[m_pblk→ino]── ino ──[android_fs]── 파일 경로
    순으로 키를 따라가며 연결한다. 연결이 안 되는 구간은 None 으로 남긴다.
    """
    # 1) 계층 간 배수와 각 계층의 지연을 먼저 구한다.
    ratio = _detect_ratio(p)              # sector ↔ LBA 배수
    ufs_lat = _ufs_latencies(p)           # UFS device 지연(체인의 기준 축)
    blk = _block_latencies(p)             # sector → 블록 지연/comm
    part_off = _infer_partition_offset(p, ratio)   # 파일↔디바이스 다리(오프셋)
    ino_file = _ino_to_file(p)            # ino → (경로, op)
    # f2fs_map 으로 만든 물리블록→inode 역인덱스(파일 귀속에 사용).
    pblk_ino = {fm["pblk"]: fm["ino"] for fm in p.f2fs_map if fm["pblk"] is not None}

    chains = []
    for u in ufs_lat:                     # UFS 명령(완료된 것)마다 한 체인
        lba = u["lba"]
        chain = {"ufs": u, "block": None, "file": None}
        if lba is not None:
            # 2) UFS → block: LBA 를 sector 로 환산해 같은 sector 의 블록 요청을 찾음.
            sector = lba * ratio
            chain["block"] = blk.get(sector)
            # 3) block → 파일(추정): 오프셋을 알면 sector 를 파티션 내 f2fs 블록으로
            #    되돌리고(pblk), 그 pblk 가 어느 inode 인지, 그 inode 의 경로가
            #    무엇인지 차례로 조회한다.
            if part_off is not None:
                pblk = (sector - part_off) // ratio
                ino = pblk_ino.get(pblk)
                if ino is not None and ino in ino_file:
                    path, op = ino_file[ino]
                    chain["file"] = {"ino": ino, "path": path, "op": op}
        chains.append(chain)
    # ratio/part_off 는 리포트 헤더에서 추정값을 보여주기 위해 함께 반환.
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
    A(" Android ftrace 흐름 추적 분석 리포트")
    A("=" * 70)
    A(f" 파싱 라인: {p.total}  (인식 이벤트: {p.matched})")
    A(f" 이벤트 수 — ufs:{len(p.ufs)} block_issue:{len(p.block_issue)} "
      f"scsi:{len(p.scsi)} f2fs_map:{len(p.f2fs_map)} android_fs:{len(p.android_fs)} "
      f"io_latency:{len(p.io_latency)}")
    A(f" sector=LBA×{corr['ratio']} 로 추정, 파티션 오프셋(sector) 추정: {corr['part_off']}")
    if not corr["ufs_lat"]:
        A("")
        A(" [안내] ufshcd_command(send/complete) 가 없어 UFS 흐름 추적을 만들 수 없습니다.")
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

    # 흐름 추적 체인 (앞에서 limit 개)
    matched_file = sum(1 for c in corr["chains"] if c["file"])
    matched_block = sum(1 for c in corr["chains"] if c["block"])
    A("")
    A(f" ── 흐름 추적 체인 (UFS↔block↔파일, 상위 {min(limit, len(corr['chains']))}건) ──")
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
        description="Android ftrace 로그 흐름 추적 분석기")
    ap.add_argument("logfile", help="분석할 캡처 .log 파일")
    ap.add_argument("-o", "--output", help="리포트를 저장할 파일(미지정 시 화면 출력)")
    ap.add_argument("--limit", type=int, default=50, help="흐름 추적 체인 출력 개수(기본 50)")
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
