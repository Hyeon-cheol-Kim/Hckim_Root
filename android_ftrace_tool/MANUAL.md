# Android ftrace I/O 분석 도구 — 전체 매뉴얼

앱의 파일 I/O 가 **앱 → 파일시스템(F2FS/EXT4) → block → SCSI → UFS** 까지 내려가는
스토리지 데이터 플로우를, ftrace 로 캡처하고 계층 간 **흐름 추적(연결)** 까지 분석하는
도구입니다. 이 문서는 **모든 기능과 사용법을 예시와 함께** 설명합니다.

- 빠른 요약만 원하면 → `README.md`
- bpftrace 바이너리 빌드 → `../tools/bpftrace-android/README.md`

---

## 목차

1. [구성과 분석 스택](#1-구성과-분석-스택)
2. [요구 사항과 준비](#2-요구-사항과-준비)
3. [기능 1 — 로그 캡처 (`python -m android_ftrace_tool`)](#3-기능-1--로그-캡처)
4. [캡처 메뉴 명령 전체 레퍼런스](#4-캡처-메뉴-명령-전체-레퍼런스)
5. [기능 2 — function_graph I/O 인과 보기 (`g`)](#5-기능-2--function_graph-io-인과-보기-g)
6. [기능 3 — 흐름 추적 트리거 / io_latency 합성 이벤트 (`h`)](#6-기능-3--흐름-추적-트리거--io_latency-합성-이벤트-h)
7. [기능 4 — 사후 흐름 추적 분석기 (`analyzer`)](#7-기능-4--사후-흐름-추적-분석기-analyzer)
8. [기능 5 — bpftrace 커널-내 1:1 흐름 추적 (`bpftrace`)](#8-기능-5--bpftrace-커널-내-11-흐름-추적-bpftrace)
9. [기능 6 — 커널 eBPF 준비도 점검 (`bpftrace check`)](#9-기능-6--커널-ebpf-준비도-점검-bpftrace-check)
10. [기능 7 — bpftrace 바이너리 빌드 (`tools/bpftrace-android`)](#10-기능-7--bpftrace-바이너리-빌드)
11. [흐름 추적 키와 한계](#11-흐름-추적-키와-한계)
12. [엔드투엔드 시나리오 예시](#12-엔드투엔드-시나리오-예시)
13. [문제 해결(Troubleshooting)](#13-문제-해결)

---

## 1. 구성과 분석 스택

| 모듈 | 역할 | 실행 |
|------|------|------|
| `core.py` | adb 통신 + ftrace 제어 **순수 로직**(print/input 없음) | (라이브러리) |
| `cli.py` | 대화형 콘솔 UI | `python -m android_ftrace_tool` |
| `analyzer.py` | 저장된 `.log` 사후 흐름 추적 분석 | `python -m android_ftrace_tool.analyzer` |
| `bpftrace.py` | eBPF 흐름 추적 스크립트 생성·실행·준비도 점검 | `python -m android_ftrace_tool.bpftrace` |
| `tools/bpftrace-android/` | aarch64 정적 bpftrace 빌드 | `./build.sh` |

**분석 스택(목적별로 골라 쓰기):**

| 목적 | 수단 | 정확도 / 비용 |
|------|------|---------------|
| 무슨 I/O 가 일어나는지 전체 흐름 보기 | 캡처(`f`) → `.log` | 보통 / 낮음 |
| 동기 read 경로 인과를 눈으로 추적 | 캡처 `g`(function_graph) | 보통 / 중간 |
| UFS·block 지연 + 파일 연결을 표로 | 캡처 `f`(+`h`) → `analyzer` | best-effort / 낮음 |
| 정확한 지연·진짜 1:1 흐름 추적 | `bpftrace run` | 높음 / 높음(빌드 필요) |

---

## 2. 요구 사항과 준비

**PC**
- Python 3.7+
- adb(Android Platform Tools), `PATH` 등록 — 확인: `adb version`

**폰**
- 설정 → 개발자 옵션 → **USB 디버깅 ON**
- ftrace 제어에 보통 **root** 필요: `userdebug`/`eng` 빌드는 `adb root`,
  양산 빌드는 `su`(도구의 `--su`/`use_su` 우회 사용)

**연결 확인**
```bash
adb version
adb devices -l
adb root            # 가능하면. 안 되면 su 우회로 진행
```

---

## 3. 기능 1 — 로그 캡처

가장 기본. 이벤트를 골라 켜고 실시간 캡처해 `.log` 로 저장합니다.

```bash
# 저장소 루트에서
python -m android_ftrace_tool

# adb 경로 직접 지정
python -m android_ftrace_tool --adb /path/to/adb
```

진행 순서:
1. **디바이스 선택** — 목록에서 번호 입력
2. **이벤트 설정 메뉴** — (아래 4장 참고). 보통 **`f`**(플로우 프리셋) → **`s`**
3. **버퍼/옵션** 확인 후 **캡처 시작**
4. 폰에서 측정할 동작 수행(앱 실행, 파일 저장 등)
5. **Ctrl-C** → 캡처 종료 → `.log` 저장(+옵션에 따라 폰에서 pull)

**가장 흔한 사용(흐름 추적 분석 목적):**
```
1) 디바이스 선택
2) f  ← read/write/erase 플로우 전체 켜기(android_fs→f2fs→writeback→block→scsi→ufs)
   h  ← (선택) block 지연을 io_latency 합성 이벤트로 기록
   s  ← 설정 완료
3) 캡처 시작 → 앱에서 파일 저장 → Ctrl-C
```

> `android_fs` + `f2fs` 가 켜져 있어야 이후 `analyzer` 가 **파일(경로/inode)** 까지
> 연결할 수 있습니다. `f` 프리셋이 둘 다 켜줍니다.

---

## 4. 캡처 메뉴 명령 전체 레퍼런스

이벤트 설정 화면에서 쓰는 명령입니다.

| 입력 | 동작 | 예시/설명 |
|------|------|-----------|
| **번호** | 그룹 on/off 토글 | `3` → 3번 그룹 토글. 표시 `[O]`켜짐 `[ ]`꺼짐 `[X]`미지원 `[~]`일부 |
| **`f`** | **플로우 프리셋** 전체 켜기 | `android_fs→f2fs→writeback→block→scsi→ufs`(지원분만) |
| **`y`** | **sync 시스템콜** 추적 on/off | `fsync`/`fdatasync`/`sync` 등 syscall tracepoint |
| **`d`** | 켜진 그룹의 **개별 이벤트 세부 선택**(빼기) | 예: `ufs` 에서 클럭/전원 이벤트 빼고 `ufshcd_command` 만 남김 → `[~]` |
| **`g`** | **function_graph I/O 인과 보기** on/off | 5장 참고 |
| **`h`** | **흐름 추적 트리거**(block I/O 지연 → `io_latency`) on/off | 6장 참고 |
| **`t`** | tracer 설정 | `nop`(기본, 이벤트 캡처) / `function_graph` 등 |
| **`x`** | 스토리지만 보기 ↔ 전체 그룹 보기(고급) | 지원 그룹 전체 탐색 |
| **`a`** | 전체 선택 해제(트리거·그래프 설정도 정리) | 초기화 |
| **`s`** | 설정 완료 → 다음 단계 | |

**이벤트 그룹(스토리지 플로우 순):**

| 계층 | 그룹 | 설명 |
|------|------|------|
| 앱 I/O | `android_fs` | 앱→파일 매핑(read/write 시작·종료, 경로·inode·오프셋) |
| 파일시스템 | `f2fs` | read/write/fsync, **GC**, checkpoint, discard, truncate |
| 파일시스템 | `ext4` | write/할당/truncate (/data 가 ext4 인 단말) |
| 파일시스템 | `erofs` | EROFS 읽기전용(system/vendor) 읽기 |
| 저널링 | `jbd2` | EXT4 저널 커밋/체크포인트 |
| 라이트백 | `writeback` | 더티 페이지 flush(`balance_dirty_pages`) |
| 블록 | `block` | bio 큐잉/발행/완료/병합/discard |
| SCSI | `scsi` | SCSI 명령 디스패치/완료(UFS 상위) |
| UFS/UIC | `ufs` | `ufshcd_command` + `ufshcd_uic_command` |

> **GC/checkpoint/discard** 는 `f2fs` 그룹 안의 개별 이벤트라, `f2fs`(또는 `f`)를
> 켜면 자동 추적됩니다.

---

## 5. 기능 2 — function_graph I/O 인과 보기 (`g`)

`function_graph` tracer 는 함수 호출을 **들여쓰기(중첩)** 로 보여줍니다. 캡처 메뉴
에서 **`g`** 를 누르면 tracer 를 `function_graph` 로 바꾸고, I/O 진입 함수
(`core.py` 의 `IO_GRAPH_FUNCTIONS`)로 범위를 **한정**해 로그 폭발을 막습니다.

동기 read 경로가 한 덩어리로 보입니다:

```
 2207.114 |  vfs_read() {
 2207.114 |    f2fs_file_read_iter() {
 2207.115 |      submit_bio() {
 2207.116 |        scsi_queue_rq() {
 2207.117 |          ufshcd_queuecommand();
          |        }
          |      }
          |    }
          |  }
```

- 켜고 끄기: 메뉴에서 `g` 토글. 끄면 tracer 가 `nop` 으로 복귀.
- 범위 함수 수정: `core.py` 의 `IO_GRAPH_FUNCTIONS` 리스트.
- **주의**: 이 모드는 로그 형식이 "이벤트 나열"과 달라 **`analyzer` 대상이 아닙니다**.
  눈으로 인과를 따라갈 때 쓰세요.

---

## 6. 기능 3 — 흐름 추적 트리거 / io_latency 합성 이벤트 (`h`)

ftrace 의 **hist/synthetic** 기능으로, `block_rq_issue` 와 `block_rq_complete` 를
공유 키 `(dev, sector)` 로 **커널 안에서 조인**해 지연을 계산하고, 그 결과를
`io_latency` 라는 **합성 이벤트**로 같은 로그에 남깁니다.

- 켜기: 캡처 메뉴에서 **`h`**. 그러면 로그에 이런 줄이 추가됩니다:
  ```
  <idle>-0 [001] d.h1 2207.231: io_latency: lat=320 dev=... sector=2359296
  ```
- 끄기: 다시 `h`(또는 `a`). 트리거·합성 이벤트가 깨끗이 제거됩니다.
- **요구**: 커널에 `CONFIG_HIST_TRIGGERS` / `CONFIG_SYNTH_EVENTS`. 없으면 설치가
  실패하고 경고만 출력(나머지 캡처는 정상). best-effort 입니다.
- `analyzer` 는 `io_latency` 가 있으면 그 값을 block 지연으로 **우선 사용**합니다.

수동으로 직접 확인하고 싶다면(참고):
```bash
adb shell su -c 'cat /sys/kernel/tracing/events/synthetic/io_latency/hist'
```

---

## 7. 기능 4 — 사후 흐름 추적 분석기 (`analyzer`)

저장된 `.log` 를 파싱해 **UFS ↔ block ↔ 파일** 을 자동으로 스티칭하고, opcode 별
지연 요약과 흐름 추적 체인을 출력합니다.

```bash
python -m android_ftrace_tool.analyzer capture.log                  # 화면 출력
python -m android_ftrace_tool.analyzer capture.log -o report.txt    # 파일 저장
python -m android_ftrace_tool.analyzer capture.log --limit 100      # 체인 100개
```

**옵션**

| 옵션 | 의미 | 기본 |
|------|------|------|
| `logfile` | 분석할 캡처 `.log` (필수) | — |
| `-o, --output` | 리포트 저장 경로 | 화면 출력 |
| `--limit N` | 흐름 추적 체인 출력 개수 | 50 |

**출력 예시(실제 형식):**
```
======================================================================
 Android ftrace 흐름 추적 분석 리포트
======================================================================
 파싱 라인: 15  (인식 이벤트: 15)
 이벤트 수 — ufs:4 block_issue:2 scsi:2 f2fs_map:2 android_fs:2 io_latency:0
 sector=LBA×8 로 추정, 파티션 오프셋(sector) 추정: 352512

 ── UFS 명령 요약 (opcode 분류별 device 지연) ──
   분류                건수      평균us      최대us
   READ               1     340.0     340.0
   WRITE              1     234.0     234.0

 ── 흐름 추적 체인 (UFS↔block↔파일, 상위 2건) ──
   (block 매칭 2/2, 파일 추정 1/2)
   [UFS WRITE_10    LBA=294912 tag=9 dev_lat=234.0us]
        ↔ block sector=2359296 rwbs=WS nr=8 blk_lat=320.0us comm=Binder:512_3
   [UFS READ_10     LBA=344064 tag=3 dev_lat=340.0us]
        ↔ block sector=2752512 rwbs=R nr=16 blk_lat=385.0us comm=app_process64
        ↔ 파일(추정) ino=88 path=photo.jpg op=read
```

**읽는 법**
- `dev_lat` = UFS send→complete(tag 조인) device 처리 지연
- `blk_lat` = block issue→complete((dev,sector) 조인) 블록계층 왕복 지연
  (`io_latency` 합성 이벤트가 있으면 그 값 사용)
- `comm` = block 제출 프로세스(누가 일으킨 I/O 인지)
- `파일(추정)` = sector→f2fs `m_pblk`→ino→경로 의 **best-effort** 매칭

> 자동 추정: `sector = LBA × ratio` 의 ratio(보통 8)와 파티션 오프셋을 로그에서
> 추정합니다. `android_fs`/`f2fs` 가 캡처에 없으면 "파일(추정)"은 비어 있을 수 있습니다.

> **앱 I/O 이벤트 소스**: analyzer 는 `android_fs_*`(벤더 전용, 경로 제공)와
> `f2fs_dataread_start`/`f2fs_datawrite_start`(대체, ino·offset·process 제공, **경로
> 없음**) 중 **있는 것**을 사용합니다. `android_fs` 미지원 커널에서도 후자가 있으면
> inode 까지는 흐름 추적이 되고, 파일명만 `?` 로 표시됩니다.

---

## 8. 기능 5 — bpftrace 커널-내 1:1 흐름 추적 (`bpftrace`)

로그 후처리(analyzer)는 best-effort 입니다. **정확한 지연·진짜 1:1 흐름 추적**이
필요하면 bpftrace 가 eBPF 로 **커널 안에서** 조인 키별 맵을 잡아 그 자리에서 지연을
계산합니다(로그 파싱 불필요).

**서브커맨드**
```bash
python -m android_ftrace_tool.bpftrace list                 # 스크립트 목록
python -m android_ftrace_tool.bpftrace show  <name>         # 본문 보기
python -m android_ftrace_tool.bpftrace save  <name> -o x.bt # 파일로 저장
python -m android_ftrace_tool.bpftrace run   <name> --bpftrace <폰경로> [옵션]
python -m android_ftrace_tool.bpftrace check [옵션]         # 9장 참고
```

**`run` 옵션**

| 옵션 | 의미 | 기본 |
|------|------|------|
| `--bpftrace` | 디바이스의 bpftrace 바이너리 경로(필수) | — |
| `--duration` | 실행 시간(초) | 10 |
| `-s, --serial` | 대상 디바이스 시리얼 | 자동 |
| `--su` | `su -c` 로 권한 우회(양산 빌드) | off |

**제공 스크립트**

| 스크립트 | 조인 키 | 산출 |
|----------|---------|------|
| `block_latency` | (dev, sector) | 블록 왕복 지연을 **제출 comm·rwbs별** 히스토그램 |
| `ufs_latency` | tag(send↔complete) | UFS device 지연을 **opcode별** 히스토그램 |
| `vfs_rw_latency` | tid | vfs read/write 동기 경로 지연(프로세스별) |
| `read_to_device` | 같은 tid | `read()` 구간에 발생한 block 제출 귀속(동기 read 인과) |

**예시 — 블록 지연 10초 측정:**
```bash
python -m android_ftrace_tool.bpftrace run block_latency \
       --bpftrace /data/local/tmp/bpftrace --duration 10 --su
```
출력(예):
```
@lat_us[kworker/u16:3, WS]:
[16K, 32K)   12 |@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@|
[32K, 64K)    3 |@@@@@@@@@@@@                                     |
@lat_us[app_process64, R]:
[256, 512)   45 |@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@|
```

**`save` 로 뽑아 직접 실행(참고):**
```bash
python -m android_ftrace_tool.bpftrace save ufs_latency -o ufslat.bt
adb push ufslat.bt /data/local/tmp/
adb shell su -c '/data/local/tmp/bpftrace /data/local/tmp/ufslat.bt'
```

> tracepoint 인자 이름(`args.str`/`args.tag`/`args.opcode` 등)은 커널마다 다를 수
> 있습니다. `show` 로 본문 상단의 "필드 확인" 주석을 보고
> `.../events/ufs/ufshcd_command/format` 와 맞추세요.

---

## 9. 기능 6 — 커널 eBPF 준비도 점검 (`bpftrace check`)

bpftrace 를 돌리기 전에 **커널이 eBPF 를 지원하는지** 자동 진단합니다(헛수고 방지).

```bash
python -m android_ftrace_tool.bpftrace check -s SERIAL --su
# 바이너리까지 함께 점검
python -m android_ftrace_tool.bpftrace check \
       --bpftrace /data/local/tmp/bpftrace --su
```

점검 항목: root 권한, 커널 버전, **BTF**(`/sys/kernel/btf/vmlinux`), tracefs,
`CONFIG_BPF_SYSCALL`/`BPF_EVENTS`(필수), `DEBUG_INFO_BTF`/`KPROBES`/
`FTRACE_SYSCALLS`/`UPROBES`, (옵션) bpftrace 바이너리.

**출력 예시(준비 완료):**
```
커널 eBPF 준비도 점검:
  ✅ root 권한                uid=0
  ✅ 커널 버전                  5.15.78-android13-gki
  ✅ BTF vmlinux            /sys/kernel/btf/vmlinux 있음 (CO-RE 가능)
  ✅ tracefs                마운트됨
  ✅ CONFIG_BPF_SYSCALL     =y — bpf() 시스템콜(필수)
  ✅ CONFIG_BPF_EVENTS      =y — tracepoint/kprobe 에 BPF 연결(필수)
  ✅ CONFIG_DEBUG_INFO_BTF  =y — BTF/CO-RE(kprobe 스크립트에 강력 권장)
  ...
  결론: ✅ bpftrace 사용 준비 완료.
```

- **❌ 필수 미충족** → bpftrace 어려움. ftrace 기반(`g`/`h`/analyzer)으로 가거나
  커널 재빌드.
- **⚠️ 경고** → 동작은 하지만 kprobe 스크립트(`vfs_*`)가 제한될 수 있음.

> `/proc/config.gz` 가 없는 단말은 config 항목을 "확인 불가(warn)"로 표시합니다.

---

## 10. 기능 7 — bpftrace 바이너리 빌드

`run` 에 쓸 폰용 bpftrace 바이너리를 구하는 3가지 방법입니다.

- **방법 A (권장, AOSP 환경)**: `external/bpftrace` 를 `m bpftrace` 로 빌드
  ```bash
  source build/envsetup.sh && lunch <target>-userdebug
  m bpftrace
  adb push out/target/product/<device>/system/bin/bpftrace /data/local/tmp/
  ```
- **방법 B (빠름)**: 이미 만들어진 **정적 aarch64** 바이너리를 push.
  Android 는 bionic 이라 **반드시 정적(static) 빌드**여야 실행됩니다.
  ```bash
  adb push bpftrace /data/local/tmp/
  adb shell su -c 'chmod 755 /data/local/tmp/bpftrace'
  adb shell su -c '/data/local/tmp/bpftrace --info'   # 동작 확인
  ```
- **방법 C (DIY, 재현성)**: `tools/bpftrace-android/` 의 Docker 로 직접 정적 빌드
  ```bash
  cd tools/bpftrace-android
  ./build.sh                       # out/bpftrace 생성
  file out/bpftrace                # "statically linked, ARM aarch64" 확인
  adb push out/bpftrace /data/local/tmp/
  ```
  자세한 내용·문제해결은 `tools/bpftrace-android/README.md`.

빌드/푸시 후 항상 `bpftrace check --bpftrace ...` 로 동작을 확인하세요.

---

## 11. 흐름 추적 키와 한계

ftrace 에는 계층을 관통하는 단일 ID 가 없습니다. 다음 **조인 키**로 연결합니다.

| 구간 | 조인 키 |
|------|---------|
| block ↔ scsi ↔ ufs | **sector / LBA** (device sector = LBA × 논리블록/512, 보통 ×8) |
| 파일 ↔ 블록 | **`f2fs_map_blocks` 의 m_pblk + 파티션 오프셋** |
| 앱 ↔ 파일 | **inode(ino) + 파일 오프셋** (`android_fs`/`f2fs`) |

**왜 1:1 보장이 어려운가**
- **read 캐시 히트**: 페이지캐시에 있으면 하위(block/ufs) 명령이 아예 없음
- **readahead/병합**: 한 read 가 여러 블록을 미리 읽거나, 여러 요청이 하나로 병합
- **비동기 writeback**: write 는 앱 컨텍스트가 아니라 `kworker` 가 나중에 flush

그래서 `analyzer` 의 "파일(추정)"과 시간 기반 매칭은 **best-effort** 입니다.
정밀이 필요하면 **bpftrace**(커널-내 조인)를 쓰세요.

---

## 12. 엔드투엔드 시나리오 예시

### 시나리오 A — "앱이 사진을 저장할 때 어떤 UFS write 가 나가나"
```bash
# 1) 캡처 설정: 플로우 + 블록지연 합성
python -m android_ftrace_tool
#   → 디바이스 선택 → f → h → s → 캡처 시작
# 2) 폰에서 카메라로 사진 저장
# 3) Ctrl-C 로 종료 → photo_save.log 저장
# 4) 흐름 추적 분석
python -m android_ftrace_tool.analyzer photo_save.log -o photo_report.txt
#   → WRITE_10 ↔ block(sector,comm=kworker) ↔ 파일(추정) 체인 확인
```

### 시나리오 B — "앱 실행 시 read 지연이 어디서 큰가" (정밀)
```bash
# 0) 준비도 점검
python -m android_ftrace_tool.bpftrace check --bpftrace /data/local/tmp/bpftrace --su
# 1) UFS device 지연(opcode별)
python -m android_ftrace_tool.bpftrace run ufs_latency \
       --bpftrace /data/local/tmp/bpftrace --duration 15 --su
# 2) 같은 구간 vfs read 지연(프로세스별)과 비교
python -m android_ftrace_tool.bpftrace run vfs_rw_latency \
       --bpftrace /data/local/tmp/bpftrace --duration 15 --su
#   → vfs 지연은 큰데 ufs 지연이 작으면 캐시미스/CPU/락 쪽, 둘 다 크면 디바이스 병목
```

### 시나리오 C — "F2FS GC 가 도는 동안 I/O 영향"
```bash
python -m android_ftrace_tool
#   → 디바이스 선택 → 3(f2fs) → 7(block) → s → 장시간 캡처
#   f2fs GC/checkpoint/discard 이벤트와 block 발행을 같은 타임라인에서 확인
```

---

## 13. 문제 해결

| 증상 | 원인/해결 |
|------|-----------|
| `adb 실행 파일을 찾을 수 없습니다` | Platform Tools 설치·PATH 확인, 또는 `--adb /경로` |
| 디바이스가 안 보임 | USB 디버깅 ON, 케이블/`adb devices` 확인, 폰의 인증 팝업 허용 |
| tracefs 를 못 찾음 | root 필요. `adb root` 또는 도구의 su 우회. 커널이 tracefs 미지원일 수 있음 |
| 이벤트가 `[X]`(미지원) | 해당 커널이 그 tracepoint 를 안 가짐(정상). 지원분만 사용 |
| `h` 설치 실패 경고 | `CONFIG_HIST_TRIGGERS`/`CONFIG_SYNTH_EVENTS` 없음. 캡처 자체는 정상 진행 |
| analyzer 에서 "파일(추정) 0/N" | `android_fs`/`f2fs` 미캡처, 또는 파티션 오프셋 추정 실패. `f` 프리셋으로 재캡처 |
| `android_fs` 가 `[X]`(미지원) | 벤더 전용 그룹이라 GKI 등엔 없음. `f2fs`(특히 `f2fs_map_blocks` + `f2fs_dataread_start`)로 대체 — 경로명만 빠지고 inode·LBA 흐름 추적은 정상 |
| `syscalls` 가 `[X]`(미지원) | `CONFIG_FTRACE_SYSCALLS` 없음. fsync 등은 `f2fs_sync_file_enter/exit`(f2fs 그룹) 또는 bpftrace `vfs_rw_latency` 로 대체 |
| analyzer 에서 ufs 0건 | `ufs` 그룹 미캡처. `f` 또는 `ufs` 켜고 재캡처 |
| bpftrace `CANNOT LINK EXECUTABLE` | 동적 링크 바이너리. **정적(static) aarch64** 빌드 필요(10장) |
| bpftrace 가 kprobe 에서 실패 | BTF/`CONFIG_KPROBES` 부족. `bpftrace check` 로 확인 |
| `run` 출력이 비어 있음 | 측정 구간에 해당 I/O 가 없었음. `--duration` 늘리고 그 사이 동작 유발 |
| ufs 스크립트 필드 오류 | 커널별 인자명 차이. `show` 주석대로 `args.*` 를 `.../format` 에 맞춤 |

---

문의/확장: UI 는 `cli.py` 에만 격리돼 있어, `core.py` API 를 그대로 호출하는
GUI(`gui.py`)를 새로 붙여도 로직 수정이 필요 없습니다(README "아키텍처" 참고).
