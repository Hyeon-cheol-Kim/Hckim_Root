# 개발 로그 (DEVLOG) — 문답 기록

이 문서는 이 저장소 작업의 **대화(문답) 흐름**을 그대로 누적 기록한다. 각 문답은
`Q#`(사용자 요청) → `A#`(한 일/답변) → `커밋` 순서이며, **나중에 바뀐 결정·구현은
🔄 [변경됨] 마커**로 어디서 어떻게 바뀌었는지 연결한다. (규칙: `CLAUDE.md`)

- 작업 브랜치: `claude/android-ftrace-log-tool-ivhpy9`
- 용어: 계층 간 이벤트 연결 = **흐름 추적**(영문 식별자 `correlation` 등은 유지)
- 표기: 🔄 [변경됨] = 이후 문답에서 수정됨 / 🆕 = 새로 도입 / 🐞 = 버그 수정

---

## Q1. (06-14) 흐름 추적 4종 추가 (A·B·C·D 전부 선택)
**요청**: function_graph 프리셋(A), hist/synthetic 트리거(B), 사후 분석 스크립트(C),
문서화(D)를 모두 추가.

**A1**:
- 🆕 (A) `g` — function_graph 로 I/O 호출 중첩 보기(`IO_GRAPH_FUNCTIONS` 범위 한정)
  🔄 [변경됨 → Q14] function_graph 미지원 커널용 **이벤트 스택트레이스 대체** 추가.
- 🆕 (B) `h` — `block_rq_issue↔complete` 를 (dev,sector)로 커널 조인 → `io_latency`
  합성 이벤트. 계산식 `io_latency(µs)=T_complete−T_issue`.
  🔄 [변경됨 → Q15] 실패 원인 진단 추가. 🔄 [변경됨 → Q17] 문법 변형 자동선택.
- 🆕 (C) `analyzer.py` — `.log` 파싱 후 UFS↔block↔파일 스티칭 + 지연 요약.
  🔄 [변경됨 → Q12] `f2fs_dataread_start` 등 android_fs 대체 소스 지원.
- 🆕 (D) README 의 조인 키/한계 문서화.

**커밋**: `6d99149`

---

## Q2. (06-14) "추가해줘" — bpftrace 연동
**요청**: 정밀 1:1 상관용 bpftrace 스크립트 생성기 추가.

**A2**: 🆕 `bpftrace.py` — `list/show/save/run`. 스크립트 `block_latency`,
`ufs_latency`, `vfs_rw_latency`, `read_to_device`. `core.Adb.push()` 추가.
🔄 [변경됨 → Q5] `check` 서브커맨드 추가. 🔄 [변경됨 → Q14] `io_callstack` 추가.

**커밋**: `e162369`

---

## Q3. (06-14) "이건 어떻게 사용할 수 있어?"
**A3**: (코드 변경 없음) 캡처→analyzer→bpftrace 사용 흐름 설명.

## Q4. (06-14) "Bpftrace 바이너리는 어떻게 만들지?"
**A4**: (코드 변경 없음) 방법 A(AOSP `m bpftrace`)/B(정적 바이너리)/C(Docker
크로스컴파일) 설명. 이어서 ①준비도 체크 ②Docker 빌드 추가를 제안.

---

## Q5. (06-14) "둘다 추가하고 자세한 메뉴얼 만들어줘"
**요청**: eBPF 준비도 체크 + aarch64 정적 빌드 도구 + 전체 매뉴얼.

**A5**:
- 🆕 `bpftrace check` — root/BTF/tracefs/CONFIG_*/바이너리 ✅⚠️❌ 진단.
- 🆕 `tools/bpftrace-android/`(Dockerfile, build.sh, README) — musl 정적 빌드.
- 🆕 `android_ftrace_tool/MANUAL.md` — 전 기능·예시 매뉴얼.

**커밋**: `ae36487`

---

## Q6. (06-14) "상관이라는 표현대신 이해하기 좋은 단어로"
**요청**: 용어 변경. 선택 결과 = **"흐름 추적"**, 코드 영문 식별자는 유지.

**A6**: 🔄 [변경됨] 문서·주석·UI 의 "상관" → **"흐름 추적"** 일괄 변경(Q1~Q5 에서
쓰던 "상관 분석기/상관 트리거/상관 체인" 표현이 여기서 모두 교체됨). 더불어
오늘 작업 코드에 상세 주석 보강.

**커밋**: `2fd12c2`

---

## Q7. (06-14) "추가해줘" — 주석 규칙 고정
**A7**: 🆕 `CLAUDE.md` 생성 — "모든 코드에 상세 주석 필수" 등 작업 규칙 명문화.
**커밋**: `4423b7d`

---

## Q8. (06-14) "새 파일은 코드창(기능)별 폴더로"
**요청**: 새 파일을 기능/도구 단위 폴더에. 기존 루트 파일도 정리.

**A8**: 🔄 [변경됨] 루트에 흩어져 있던 PAM4 관련 파일을 `eye_diagram_converter/`
폴더로 `git mv`(구조 변경). `CLAUDE.md` 에 폴더 규칙 추가.
**커밋**: `18f5c82`

---

## Q9. (06-16) "Bpftrace 의 경로는?"
**A9**: (코드 변경 없음) 저장소 내(`bpftrace.py`, `tools/bpftrace-android/`) /
폰(`/data/local/tmp/bpftrace`) / 빌드 산출물 경로 설명.

## Q10. (06-16) "events/bpf_trace 가 bpftrace 맞아?"
**A10**: (코드 변경 없음) 아니오 — `events/bpf_trace` 는 커널 tracepoint 그룹,
bpftrace 는 별도 사용자공간 바이너리. 구분 설명 + `check` 권장.

---

## Q11. (06-16) "android_fs 미지원이면 이걸 추가, syscalls 해결책도"
**요청**: android_fs 대체로 f2fs 앱 I/O 이벤트 인식 추가 + syscalls 미지원 대응.

**A11**: 🆕 analyzer 가 `f2fs_dataread_start`/`f2fs_datawrite_start` 파싱
(ino/pos/len/cmdline/pid; 경로는 미제공 → `?`). 리포트 라벨 `android_fs`→`app_fs`.
syscalls 는 다음 문답에서 처리.
**커밋**: `f38d47e`

---

## Q12. (06-16) "syscalls 제외하고 f2fs 레이어 fsync 로"
**요청**: `y`(sync) 를 syscalls 대신 f2fs/ext4 fsync 이벤트로.

**A12**: 🔄 [변경됨] Q1 의 `sync_syscalls`(syscalls 그룹) 묶음을 **`sync_events`**
(`f2fs_sync_file_enter/exit`, `f2fs_write_checkpoint`, ext4 동등)로 교체.
묶음 토글이 없는 그룹은 통째로 제외하고 있는 것만 켜도록 수정.
**커밋**: `d4edd5e`

---

## Q13. (06-16) "function_graph 미지원, 대체 방법?"
**전제**: 사용자 커널에 `f2fs_sync_file_enter` 있음, function_graph 없음.

**A13**: 🔄 [변경됨] Q1 의 `g` 를 확장 — function_graph 있으면 그대로, **없으면
이벤트 스택트레이스로 자동 대체**(`STACK_TRACE_EVENTS` 에 stacktrace 트리거).
🆕 bpftrace `io_callstack`(block 제출 kstack 집계).
🔄 [변경됨 → Q16] 이 스택트레이스가 재설치 시 실패하는 버그를 이후 수정.
**커밋**: `5bc9f10`

---

## Q14. (06-16) "흐름 추적 트리거 설치 실패 (trigger 파일은 있음)"
**A14**: 🆕 `diagnose_hist_support()` — 실패 원인을 권한 / hist 미지원 /
synthetic 미지원 / 문법차이로 구분해 안내. "trigger 파일 존재 ≠ hist 지원" 설명.
**커밋**: `91975bd`

## Q15. (06-16) "echo 리다이렉션이 실패한 것 같다, 확인해줘"
**A15**: (확인) 생성 명령은 `_write`(이벤트 켜기, 정상)와 **동일 메커니즘**임을
재현 확인 → 리다이렉션 문제 아님, 커널이 trigger 내용을 거부한 것. (Q14 진단에 포함)

---

## Q16. (06-16) "hist/synthetic 은 되는데 실패한다고 나옴"
**요청**: onmatch/필드 문법 차이 대응.

**A16**: 🔄 [변경됨] Q1 의 단일 트리거 세트를 **변형(variants) 구조**로 변경.
V1 `.io_latency($lat,dev,sector)` → V2 `.trace(io_latency,...)` → V3 `lat`만(타입
불일치 회피) 순서로 시도, 결과 이벤트 생성 확인 후 채택(실패분 롤백).
**커밋**: `87dc183`

---

## Q17. (06-16) "스택트레이스가 되던 게 이 수정으로 안 됨"
**A17**: 🐞 [버그수정] 원인 = 트리거가 커널에 잔류 → 재설치 시 "File exists" 로
**조용히 실패**. Q13 의 `apply_event_stacktrace` 를 **설치 전 제거(멱등)** 로 바꾸고,
실패를 `[제외] group/event: 사유` 로 노출하도록 수정.
**커밋**: `0bb336c`

---

## Q18. (06-16) "io_latency 가 어떻게 계산되는거지?"
**A18**: (코드 변경 없음) `io_latency(µs)=T_complete−T_issue`(같은 dev,sector).
issue 트리거가 `ts0=common_timestamp.usecs` 저장 → complete 트리거가
`lat=...-$ts0` 후 `onmatch(...).io_latency(...)` 발행. 블록 계층 왕복(큐잉+디바이스).

## Q19. (06-16) "지금까지 대화도 문서로 저장, 계속 갱신"
**A19**: 🆕 `docs/DEVLOG.md` 생성 + `CLAUDE.md` 에 "개발 로그(필수, 누적)" 규칙.

## Q20. (06-16) "문답 형식으로, 변경된 부분 표시"
**A20**: 🔄 [변경됨] 본 문서를 **문답 형식 + 변경 마커(🔄/🆕/🐞)** 로 재작성(Q19 의
요약형 로그를 대체).

---

## 변경 이력 요약 (무엇이 나중에 바뀌었나)

| 처음(문답) | 나중에 바뀜(문답) | 무엇이 바뀌었나 |
|------------|-------------------|------------------|
| Q1 `g` function_graph | Q13 | 미지원 커널용 이벤트 스택트레이스 대체 추가 |
| Q13 스택트레이스 | Q17 | 잔류 트리거로 재설치 실패 → 멱등 설치로 버그수정 |
| Q1 `h` 단일 트리거 | Q14, Q16 | 실패 진단 추가, 문법 변형 자동선택 |
| Q1 analyzer(android_fs) | Q11 | f2fs_dataread/datawrite 대체 소스 지원 |
| Q1 `y` sync_syscalls | Q12 | f2fs/ext4 fsync 레이어(`sync_events`)로 교체 |
| Q1~Q5 "상관" 용어 | Q6 | "흐름 추적"으로 일괄 변경 |
| 루트 흩어진 파일 | Q8 | 기능 폴더(`eye_diagram_converter/`)로 이동 |
| Q19 요약형 로그 | Q20 | 문답 형식으로 재작성 |

## 커밋 타임라인

`6d99149`(Q1) · `e162369`(Q2) · `ae36487`(Q5) · `2fd12c2`(Q6) · `4423b7d`(Q7) ·
`18f5c82`(Q8) · `f38d47e`(Q11) · `d4edd5e`(Q12) · `5bc9f10`(Q13) · `91975bd`(Q14) ·
`87dc183`(Q16) · `0bb336c`(Q17) · `bab428f`(Q19)

## 미해결 / 다음에 볼 것
- `h` 변형(V1/V2/V3)이 실 디바이스에서 어디까지 먹는지 확인.
- 스택트레이스 부착 후 실제 로그에 호출 체인이 찍히는지 확인.
- (선택) bpftrace 정적 바이너리 실제 빌드/검증.

---

> 갱신 규칙: 새 문답이 오갈 때마다 `Q#/A#` 를 추가하고, 이전 결정이 바뀌면 그
> 자리에 🔄 [변경됨 → Q#] 를 달고 "변경 이력 요약" 표도 갱신한다.
> 한 작업 = 한 커밋 + 로그 갱신.
