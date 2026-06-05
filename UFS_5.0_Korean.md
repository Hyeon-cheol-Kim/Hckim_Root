# JEDEC UFS 5.0 규격 한국어 번역 요약

> **출처**: JEDEC **JESD220H** — Universal Flash Storage (UFS) Version 5.0 (발행일: 2026년 2월 26일)  
> **원본 언어**: 영어 → **번역 언어**: 한국어  
> **작성 기준**: JEDEC 및 MIPI Alliance 공식 발표 자료 기반  
> **관련 규격**: MIPI M-PHY v6.0 / MIPI UniPro v3.0 / JESD223G

---

## 목차

1. [소개](#1-소개)
2. [용어 및 약어](#2-용어-및-약어)
3. [시스템 아키텍처](#3-시스템-아키텍처)
4. [물리 계층 (M-PHY)](#4-물리-계층-m-phy)
5. [데이터 링크 계층 (UniPro)](#5-데이터-링크-계층-unipro)
6. [전송 계층 (UTP)](#6-전송-계층-utp)
7. [응용 계층 (UAP)](#7-응용-계층-uap)
8. [UFS 명령어 집합 (UCS)](#8-ufs-명령어-집합-ucs)
9. [전력 관리](#9-전력-관리)
10. [보안 기능](#10-보안-기능)
11. [성능 특성](#11-성능-특성)
12. [디스크립터 및 레지스터](#12-디스크립터-및-레지스터)
13. [오류 처리](#13-오류-처리)
14. [UFS 5.0 주요 변경사항](#14-ufs-50-주요-변경사항)
15. [UFS 4.1 vs UFS 5.0 상세 비교](#15-ufs-41-vs-ufs-50-상세-비교)
16. [MIPI M-PHY v6.0 규격](#16-mipi-m-phy-v60-규격)
17. [MIPI UniPro v3.0 규격](#17-mipi-unipro-v30-규격)

---

## 1. 소개

### 1.1 개요

UFS(Universal Flash Storage)는 JEDEC(Joint Electron Device Engineering Council)에서 제정한 플래시 메모리 인터페이스 표준이다. 스마트폰, 태블릿, 자동차용 전자기기, 서버, IoT 기기 등 다양한 분야에서 고성능 낸드 플래시 스토리지 인터페이스로 사용된다.

UFS 5.0(**JESD220H**)은 2026년 2월 26일 JEDEC이 발행한 최신 규격으로, UFS 4.1(JESD220G) 이후의 차세대 규격이다. 다음과 같은 목표를 지향한다:

- **성능 향상**: 이전 세대 대비 순차 읽기/쓰기 대역폭 대폭 증가
- **전력 효율 개선**: 성능 당 전력 소비 절감
- **기능 확장**: 보안, 신뢰성, 다중 스트림 등 기능 강화
- **차량용(Automotive) 요구사항 지원**: 내구성, 온도 범위, 기능 안전성

### 1.2 적용 범위

본 규격은 UFS 장치(Device)와 호스트(Host) 사이의 인터페이스를 정의하며, 다음 항목을 포함한다:

- 물리 계층 신호 특성
- 프로토콜 스택 (M-PHY / UniPro / UTP / UAP)
- 명령어 집합 (SCSI 기반)
- 전력 모드 및 전력 관리 절차
- 보안 및 암호화 기능
- 초기화, 링크 설정, 장치 열거 절차

### 1.3 규격 계층 구조

UFS는 MIPI Alliance의 M-PHY 및 UniPro 규격 위에 JEDEC의 UTP/UAP 계층을 얹은 구조이다.

```
┌─────────────────────────────────────────────┐
│        응용 계층 (Application Layer)          │
│   파일시스템 / 운영체제 드라이버               │
├─────────────────────────────────────────────┤
│     UAP (UFS Application Protocol)           │
│   UCS 명령어 처리 / RPMB / Well-known LUN    │
├─────────────────────────────────────────────┤
│     UTP (UFS Transport Protocol)             │
│   UPIU 생성·파싱 / Task Management           │
├─────────────────────────────────────────────┤
│         UniPro (Data Link Layer)             │
│   흐름 제어 / 신뢰성 / 어드레싱               │
├─────────────────────────────────────────────┤
│         M-PHY (Physical Layer)               │
│   직렬 신호 / 차동 전송 / 클록 복원           │
└─────────────────────────────────────────────┘
```

---

## 2. 용어 및 약어

| 약어     | 영문 전체                                     | 한국어 의미                    |
| ------ | ----------------------------------------- | ------------------------- |
| UFS    | Universal Flash Storage                   | 범용 플래시 스토리지               |
| M-PHY  | Mobile Physical Layer                     | 모바일 물리 계층                 |
| UniPro | Unified Protocol                          | 통합 프로토콜                   |
| UTP    | UFS Transport Protocol                    | UFS 전송 프로토콜               |
| UAP    | UFS Application Protocol                  | UFS 응용 프로토콜               |
| UCS    | UFS Command Set                           | UFS 명령어 집합                |
| UPIU   | UFS Protocol Information Unit             | UFS 프로토콜 정보 단위            |
| LUN    | Logical Unit Number                       | 논리 유닛 번호                  |
| CDB    | Command Descriptor Block                  | 명령어 기술자 블록                |
| PRDT   | Physical Region Descriptor Table          | 물리 영역 기술자 테이블             |
| RPMB   | Replay Protected Memory Block             | 재생 방지 메모리 블록              |
| HPB    | Host Performance Booster                  | 호스트 성능 향상                 |
| WB     | Write Booster                             | 쓰기 향상                     |
| TW     | Turbo Write                               | 터보 쓰기 (WB의 구 명칭)          |
| UIC    | UFS Interconnect                          | UFS 상호연결 계층               |
| TMF    | Task Management Function                  | 작업 관리 기능                  |
| OCS    | Overall Command Status                    | 전체 명령어 상태                 |
| JEDEC  | Joint Electron Device Engineering Council | 반도체 공학 표준화 기관             |
| JESD   | JEDEC Standard                            | JEDEC 표준 번호               |
| HS     | High Speed                                | 고속 모드                     |
| PWM    | Pulse Width Modulation                    | 펄스 폭 변조 (저전력 모드)          |
| PAM4   | Pulse Amplitude Modulation 4-level        | 4레벨 펄스 진폭 변조 (UFS 5.0 신규) |
| NRZ    | Non-Return-to-Zero                        | 비귀환 제로 (기존 2레벨 신호 방식)     |
| SLC    | Single Level Cell                         | 단일 레벨 셀                   |
| MLC    | Multi Level Cell                          | 다중 레벨 셀                   |
| TLC    | Triple Level Cell                         | 3단 레벨 셀                   |
| QLC    | Quad Level Cell                           | 4단 레벨 셀                   |

---

## 3. 시스템 아키텍처

### 3.1 물리적 토폴로지

UFS 인터페이스는 **점대점(Point-to-Point)** 구조를 사용하며, 호스트와 장치 사이에 단일 링크가 형성된다.

```
┌─────────┐   TX  ──────────────────→   RX  ┌──────────┐
│         │                                  │          │
│  호스트  │   RX  ←──────────────────   TX  │  장 치   │
│  (Host) │                                  │ (Device) │
│         │   REF_CLK ──────────────────→    │          │
└─────────┘                                  └──────────┘
```

- **TX 레인**: 호스트 → 장치 방향 (다운링크)
- **RX 레인**: 장치 → 호스트 방향 (업링크)
- **REF_CLK**: 호스트가 기준 클록 공급 (선택적)

### 3.2 멀티-레인 구성

UFS 5.0은 최대 **2개의 데이터 레인**을 지원한다.

| 구성     | 설명                          |
| ------ | --------------------------- |
| x1     | 단일 레인 (TX 1개, RX 1개)        |
| x2     | 듀얼 레인 (TX 2개, RX 2개), 최대 성능 |

### 3.3 논리 유닛 (LUN)

UFS 장치는 최대 **32개의 논리 유닛**을 지원한다.

| LUN 유형           | 설명                  |
| ---------------- | ------------------- |
| 일반 LUN (LUN 0–7) | 사용자 데이터 저장 영역       |
| Well-known LUN   | 특수 목적 LUN (아래 표 참조) |

**Well-known LUN 목록:**

| Well-known LUN    | 주소     | 용도             |
| ----------------- | ------ | -------------- |
| W-LUN REPORT LUNS | 0xC1   | 지원 LUN 목록 조회   |
| W-LUN UFS DEVICE  | 0xC0   | 장치 전체 제어       |
| W-LUN BOOT        | 0xB0   | 부팅 파티션         |
| W-LUN RPMB        | 0xC4   | 보안 재생방지 메모리 블록 |

---

## 4. 물리 계층 (M-PHY)

### 4.1 개요

UFS의 물리 계층은 MIPI Alliance의 **M-PHY 규격**을 따른다. M-PHY는 차동 신호 방식의 직렬 인터페이스로, 고속 모드(HS)와 저속 모드(PWM)를 모두 지원한다.

**UFS 5.0의 핵심 변경**: 기존 NRZ(2레벨) 신호 방식에서 **PAM4(4레벨 펄스 진폭 변조)** 방식으로 전환하여 동일한 보 레이트(Baud Rate)에서 데이터 전송률을 2배로 증가시켰다. PAM4는 심볼 하나당 2비트를 인코딩하므로, 같은 물리적 신호 속도에서 2배의 대역폭을 달성한다.

### 4.2 동작 모드

#### 4.2.1 고속(HS) 모드

HS 모드는 **Burst Mode**로 동작하며, 고속 데이터 전송에 사용된다.

| 기어 (Gear)     | 신호 방식      | 레인당 속도          | x1 최대 속도        | x2 최대 속도         | 도입 버전       |
| ------------- | ---------- | --------------- | --------------- | ---------------- | ----------- |
| HS-G1         | NRZ        | 1.248 Gbps      | ~150 MB/s       | ~300 MB/s        | UFS 1.0     |
| HS-G2         | NRZ        | 2.496 Gbps      | ~300 MB/s       | ~600 MB/s        | UFS 1.0     |
| HS-G3         | NRZ        | 4.992 Gbps      | ~600 MB/s       | ~1,200 MB/s      | UFS 2.0     |
| HS-G4         | NRZ        | 9.984 Gbps      | ~1,200 MB/s     | ~2,900 MB/s      | UFS 3.0     |
| HS-G5         | NRZ        | 23.2 Gbps       | ~2,900 MB/s     | ~5,800 MB/s      | UFS 4.0     |
| **HS-G6**     | **PAM4**   | **46.694 Gbps** | **~5,800 MB/s** | **~10,800 MB/s** | **UFS 5.0** |

> **UFS 5.0 핵심**: **HS-G6 + PAM4** 도입으로 레인당 최대 46.694 Gbps 달성 (출처: MIPI Alliance 공식 발표, 2026.02). HS-G5 대비 동일 보 레이트에서 PAM4를 적용해 유효 대역폭 2배 증가.

#### 4.2.2 저속(PWM) 모드

PWM 모드는 초기화, 저전력 연결 유지에 사용된다.

| 기어     | 속도       |
| ------ | -------- |
| PWM-G1 | 3 Mbps   |
| PWM-G2 | 6 Mbps   |
| PWM-G3 | 12 Mbps  |
| PWM-G4 | 24 Mbps  |
| PWM-G5 | 48 Mbps  |
| PWM-G6 | 96 Mbps  |
| PWM-G7 | 192 Mbps |

### 4.3 직렬화 및 역직렬화 (SerDes) 및 라인 인코딩

M-PHY는 기어별로 서로 다른 라인 인코딩을 적용한다.

| 기어 범위      | 인코딩       | 비고                               |
| ---------- | --------- | -------------------------------- |
| HS-G1 ~ G3 | 8b/10b    | DC 밸런스, 클록 복원                    |
| HS-G4 ~ G5 | 128b/132b | 오버헤드 ~3%로 감소                     |
| **HS-G6**  | **1b1b**  | **신규 — 8b10b 대비 오버헤드 최대 20% 절감** |

**1b1b 인코딩 (M-PHY v6.0 신규)**: PAM4의 2비트/심볼 전송을 그대로 활용하되, DC 밸런스와 클록 복원은 스크램블링(Scrambling)·프리코딩(Precoding)·그레이 코딩(Gray Coding)으로 처리하여 별도의 라인 코딩 오버헤드를 없앤다. 출처: MIPI Alliance 공식 보도자료(2026.02).

### 4.4 PAM4 신호 방식 (UFS 5.0 신규)

#### 4.4.1 NRZ vs PAM4 비교

기존 NRZ(Non-Return-to-Zero) 방식은 신호 레벨이 '0'과 '1' 두 가지뿐이어서 심볼당 1비트를 전송한다. UFS 5.0에서 도입한 **PAM4**는 신호 레벨을 4단계(00, 01, 10, 11)로 확장하여 심볼당 2비트를 전송한다.

```
NRZ (HS-G5):                PAM4 (HS-G6):
                             3 ─ ─ ─ ─ ─ ─ ─ ─  (11)
1 ─ ─ ─ ─ ─ ─ ─ ─           2 ─ ─ ─ ─ ─ ─ ─ ─  (10)
                             1 ─ ─ ─ ─ ─ ─ ─ ─  (01)
0 ─ ─ ─ ─ ─ ─ ─ ─           0 ─ ─ ─ ─ ─ ─ ─ ─  (00)

심볼당 1비트                 심볼당 2비트 (2배 효율)
```

#### 4.4.2 PAM4의 장단점

| 항목         | 내용                                                                         |
| ---------- | -------------------------------------------------------------------------- |
| **장점**     | 동일 보 레이트에서 2배 데이터 전송률, 주파수 대역폭 불변                                          |
| **단점**     | 신호 레벨 간격 감소 → SNR(신호 대 잡음비) 요구 증가                                          |
| **FEC 요구** | 신호 품질 저하 보완을 위해 **RS-FEC 적용** (UniPro v3.0)                                |
| **링크 등화기** | M-PHY v6.0에서 **선택적(Optional)** 적용 — 성능 마진 확대와 상호운용성 향상 목적 (출처: MIPI 공식 발표) |

#### 4.4.3 PAM4와 FEC

PAM4는 NRZ 대비 심볼 간 레벨 차이가 1/3로 줄어 비트 오류율(BER)이 높아진다. 이를 보상하기 위해 UFS 5.0은 **RS(Reed-Solomon) FEC** 등 전방향 오류 정정을 M-PHY 계층에서 처리한다.

### 4.5 신호 레벨

| 파라미터       | NRZ (HS-G1~G5)         | PAM4 (HS-G6)                          |
| ---------- | ---------------------- | ------------------------------------- |
| 차동 신호 진폭   | 200 mVpp (typ)         | 200 mVpp (full scale, 레벨 간격 ~67 mVpp) |
| 공통 모드 전압   | 0~0.7 V                | 0~0.7 V                               |
| 신호 임피던스    | 50 Ω (단종단), 100 Ω (차동) | 50 Ω (단종단), 100 Ω (차동)                |
| 신호 레벨 수    | 2 (0, 1)               | 4 (0, 1, 2, 3)                        |

### 4.6 링크 초기화 절차

1. **HIBERN8 해제**: 장치가 저전력 상태에서 깨어남
2. **라인 초기화**: TX/RX 트레이닝 시퀀스
3. **심볼 동기화**: COMMA 심볼로 비트 정렬
4. **HS 모드 전환**: PWM → HS 전환 (필요 시)
5. **기어 협상**: 호스트·장치 간 최대 공통 기어 선택
6. **PAM4 협상** (UFS 5.0): 양측이 HS-G6 지원 시 PAM4 모드로 전환, FEC 활성화 및 등화기(Equalizer) 트레이닝 수행

---

## 5. 데이터 링크 계층 (UniPro)

### 5.1 개요

UniPro(Unified Protocol)는 MIPI Alliance 규격으로, M-PHY 위에서 동작하는 데이터 링크·네트워크 계층이다. 패킷 기반 전송, 흐름 제어, 오류 감지·복구를 담당한다.

### 5.2 계층 구조

```
UniPro 스택
├── 네트워크 계층 (Network Layer, L3)
│   └── 소스/목적지 주소 지정 (DeviceID, CPortID)
├── 데이터 링크 계층 (Data Link Layer, L2)
│   ├── 프레임 생성/파싱
│   ├── 흐름 제어 (Flow Control, FC)
│   └── 재전송 제어 (ARQ)
└── PHY 어댑터 계층 (PHY Adapter, PA)
    └── M-PHY 제어 및 기어 관리
```

### 5.3 흐름 제어

UniPro는 **크레딧 기반 흐름 제어(Credit-based Flow Control)**를 사용한다.

- 수신 측이 수신 가능한 버퍼 크기를 크레딧으로 전송 측에 통보
- 전송 측은 크레딧 내에서만 데이터 전송
- 크레딧 고갈 시 전송 중단 및 대기

### 5.4 오류 감지 및 복구

| 기능         | 설명                       |
| ---------- | ------------------------ |
| CRC        | 각 프레임에 CRC 추가하여 비트 오류 감지 |
| ARQ        | 오류 감지 시 재전송 요청 (NAK 기반)  |
| FC_PDU 타이머 | 흐름 제어 타임아웃 감지            |

### 5.5 연결 포트 (CPort)

UniPro는 **연결 포트(CPort)** 개념을 사용해 다중 논리 채널을 구성한다.

- 호스트와 장치 각각 최대 32개의 CPort 지원
- UFS에서는 CPort 0: UTP 전송용, CPort 1: UniPro 관리용

---

## 6. 전송 계층 (UTP)

### 6.1 개요

UTP(UFS Transport Protocol)는 UFS 고유 계층으로, 호스트와 장치 간 명령·데이터·상태 정보를 UPIU(UFS Protocol Information Unit) 형태로 교환한다.

### 6.2 UPIU 구조

모든 UTP 통신은 UPIU 단위로 이루어진다.

```
UPIU 기본 헤더 (12 바이트)
├── Transaction Code (1 바이트): UPIU 유형
├── Flags (1 바이트)
├── LUN (1 바이트)
├── Task Tag (1 바이트)
├── Initiator ID / Target ID (1 바이트)
├── Command Set Type / Query Function (1 바이트)
├── Response (1 바이트)
├── Status (1 바이트)
├── EHS Length (1 바이트)
├── Device Info (1 바이트)
└── Data Segment Length (2 바이트)
```

### 6.3 UPIU 유형

| Transaction Code  | 유형                            | 설명                     |
| ----------------- | ----------------------------- | ---------------------- |
| 0x01              | Command UPIU                  | 호스트 → 장치, SCSI 명령 전송   |
| 0x21              | Response UPIU                 | 장치 → 호스트, 명령 완료 응답     |
| 0x02              | Data-Out UPIU                 | 호스트 → 장치, 쓰기 데이터 전송    |
| 0x22              | Data-In UPIU                  | 장치 → 호스트, 읽기 데이터 반환    |
| 0x04              | Task Management Request UPIU  | 작업 관리 요청               |
| 0x24              | Task Management Response UPIU | 작업 관리 응답               |
| 0x16              | Query Request UPIU            | 디스크립터/플래그/속성 조회·설정     |
| 0x36              | Query Response UPIU           | 조회·설정 응답               |
| 0x1F              | NOP Out UPIU                  | 링크 연결 확인 (호스트 → 장치)    |
| 0x3F              | NOP In UPIU                   | 링크 연결 확인 응답 (장치 → 호스트) |
| 0x05              | Ready-to-Transfer UPIU        | 장치 준비 완료 신호            |
| 0x06              | Reject UPIU                   | 요청 거부                  |

### 6.4 명령 실행 흐름

#### 읽기 명령 (SCSI READ)

```
호스트                              장치
  │── Command UPIU ──────────────→  │
  │                                  │  (데이터 준비)
  │  ←─── Data-In UPIU ────────────  │
  │  ←─── Data-In UPIU ────────────  │  (여러 UPIU)
  │  ←─── Response UPIU ───────────  │
```

#### 쓰기 명령 (SCSI WRITE)

```
호스트                              장치
  │── Command UPIU ──────────────→  │
  │  ←─── Ready-to-Transfer UPIU ─  │
  │── Data-Out UPIU ─────────────→  │
  │── Data-Out UPIU ─────────────→  │  (여러 UPIU)
  │  ←─── Response UPIU ───────────  │
```

### 6.5 큐 깊이 (Queue Depth)

UFS는 **다중 태스크 큐(Multi-Tag Queue)**를 지원한다.

| 항목      | UFS 3.1   | UFS 4.0   | UFS 5.0   |
| ------- | --------- | --------- | --------- |
| 최대 큐 깊이 | 32        | 32        | 256       |

UFS 5.0에서는 큐 깊이가 최대 **256**으로 확장되어 고부하 랜덤 I/O 성능이 향상된다.

### 6.6 PRDT (Physical Region Descriptor Table)

PRDT는 DMA 전송을 위한 물리 메모리 영역 목록이다.

- 최대 256개 엔트리
- 각 엔트리: 기저 주소(64비트) + 길이(17비트, 최대 256 KB)

---

## 7. 응용 계층 (UAP)

### 7.1 개요

UAP(UFS Application Protocol)는 UFS 장치의 논리 유닛(LUN) 관리, SCSI 명령 처리, 장치 초기화 및 설정을 담당한다.

### 7.2 Query 기능

호스트는 Query Request/Response UPIU를 통해 장치의 **디스크립터(Descriptor)**, **플래그(Flag)**, **속성(Attribute)**을 읽거나 쓸 수 있다.

#### Query 함수 코드

| 코드     | 기능               |
| ------ | ---------------- |
| 0x01   | Read Descriptor  |
| 0x02   | Write Descriptor |
| 0x03   | Read Attribute   |
| 0x04   | Write Attribute  |
| 0x05   | Read Flag        |
| 0x06   | Set Flag         |
| 0x07   | Clear Flag       |
| 0x08   | Toggle Flag      |

### 7.3 디스크립터 (Descriptors)

디스크립터는 장치 특성을 기술하는 읽기 전용(또는 일부 쓰기 가능) 데이터 구조이다.

| 디스크립터 IDN       | 이름                                       | 주요 내용               |
| --------------- | ---------------------------------------- | ------------------- |
| 0x00            | Device Descriptor                        | 장치 유형, 버전, 제조사      |
| 0x01            | Configuration Descriptor                 | LUN 설정, 부팅 설정       |
| 0x02            | Unit Descriptor                          | 개별 LUN 크기, 속성       |
| 0x03            | Interconnect Descriptor                  | 지원 UniPro/M-PHY 버전  |
| 0x04            | String Descriptor                        | 제조사명, 제품명, 시리얼 번호   |
| 0x05            | Geometry Descriptor                      | 용량, 블록 크기, 할당 유닛    |
| 0x06            | Power Descriptor                         | 지원 전력 모드, 소비 전류     |
| 0x07            | Device Health Descriptor                 | 수명, 사전 EOL 경고       |
| 0x09            | Extended UFS Features Support Descriptor | UFS 5.0 확장 기능 지원 여부 |

### 7.4 플래그 (Flags)

| 플래그 IDN     | 이름               | 설명                |
| ----------- | ---------------- | ----------------- |
| 0x01        | fDeviceInit      | 장치 초기화 트리거        |
| 0x04        | fPermanentWPEn   | 영구 쓰기 방지 활성화      |
| 0x08        | fPowerOnWPEn     | 전원 인가 쓰기 방지       |
| 0x0D        | fWriteBoosterEn  | Write Booster 활성화 |
| 0x0E        | fWBBufferFlushEn | WB 버퍼 플러시 활성화     |
| 0x0F        | fHPBEn           | HPB 활성화           |

### 7.5 속성 (Attributes)

| 속성 IDN    | 이름                              | 설명            |
| --------- | ------------------------------- | ------------- |
| 0x00      | bBootLunEn                      | 부팅 LUN 선택     |
| 0x02      | bCurrentPowerMode               | 현재 전력 모드      |
| 0x04      | bActiveICCLevel                 | 활성 전류 소비 수준   |
| 0x0F      | bRefClkFreq                     | 기준 클록 주파수     |
| 0x11      | dDynCapNeeded                   | 동적 용량 요구      |
| 0x14      | wContextConf                    | 문맥 설정         |
| 0x1B      | bWriteBoosterBufferRestoringInd | WB 버퍼 복원 중 여부 |

---

## 8. UFS 명령어 집합 (UCS)

### 8.1 개요

UFS 명령어 집합(UCS)은 **SCSI 아키텍처 모델**을 기반으로 한다. 표준 SCSI 명령의 부분 집합에 UFS 전용 확장 명령이 추가된다.

### 8.2 지원 SCSI 명령어

| 명령어                    | OpCode   | 설명                 |
| ---------------------- | -------- | ------------------ |
| TEST UNIT READY        | 0x00     | 장치 준비 상태 확인        |
| REQUEST SENSE          | 0x03     | 에러 정보 조회           |
| FORMAT UNIT            | 0x04     | 장치 포맷              |
| READ (6)               | 0x08     | 6바이트 CDB 읽기        |
| WRITE (6)              | 0x0A     | 6바이트 CDB 쓰기        |
| INQUIRY                | 0x12     | 장치 식별 정보 조회        |
| START STOP UNIT        | 0x1B     | 장치 전원 상태 제어        |
| READ CAPACITY (10)     | 0x25     | 용량 정보 조회 (10바이트)   |
| READ (10)              | 0x28     | 10바이트 CDB 읽기       |
| WRITE (10)             | 0x2A     | 10바이트 CDB 쓰기       |
| SYNCHRONIZE CACHE (10) | 0x35     | 캐시 동기화             |
| WRITE BUFFER           | 0x3B     | 펌웨어 다운로드           |
| READ BUFFER            | 0x3C     | 버퍼 읽기              |
| UNMAP                  | 0x42     | 논리 블록 매핑 해제 (TRIM) |
| READ (16)              | 0x88     | 16바이트 CDB 읽기       |
| WRITE (16)             | 0x8A     | 16바이트 CDB 쓰기       |
| PRE-FETCH (16)         | 0x90     | 데이터 사전 읽기          |
| SYNCHRONIZE CACHE (16) | 0x91     | 캐시 동기화 (16바이트)     |
| REPORT LUNS            | 0xA0     | LUN 목록 조회          |
| READ CAPACITY (16)     | 0x9E     | 용량 정보 조회 (16바이트)   |

### 8.3 Security Protocol 명령어 (RPMB)

| 명령어                   | OpCode   | 설명          |
| --------------------- | -------- | ----------- |
| SECURITY PROTOCOL IN  | 0xA2     | RPMB 데이터 읽기 |
| SECURITY PROTOCOL OUT | 0xB5     | RPMB 데이터 쓰기 |

### 8.4 HPB 관련 명령어

| 명령어              | OpCode   | 설명           |
| ---------------- | -------- | ------------ |
| READ BUFFER (16) | 0x9B     | HPB 맵 데이터 읽기 |
| HPB READ (16)    | 0xE8     | HPB 힌트 포함 읽기 |

### 8.5 UNMAP (TRIM) 동작

UNMAP 명령은 더 이상 사용하지 않는 논리 블록을 장치에 알려 낸드 플래시의 가비지 컬렉션 효율을 높인다.

```
UNMAP Parameter List
├── UNMAP Data Length (2 바이트)
├── UNMAP Block Descriptor Data Length (2 바이트)
└── UNMAP Block Descriptor 배열
    └── 각 엔트리: 시작 LBA (8 바이트) + 블록 수 (4 바이트)
```

---

## 9. 전력 관리

### 9.1 전력 모드 개요

UFS 5.0은 다음과 같은 전력 상태를 지원한다:

| 상태                  | 설명                   | 복귀 시간      |
| ------------------- | -------------------- | ---------- |
| Active (HS)         | 고속 데이터 전송            | N/A        |
| Sleep               | UIC 링크 유지, 핵심 회로 저전력 | ~1 ms      |
| Hibernate (HIBERN8) | M-PHY 링크 비활성화, 최저 전력 | ~1 ms      |
| Power Down          | 완전 전원 차단             | 장치 초기화 필요  |

### 9.2 전력 소비 클래스

UFS 5.0은 장치의 최대 전류 소비를 등급별로 정의한다.

| ICC Level   | 최대 전류 (mA)     |
| ----------- | -------------- |
| Level 0     | 0              |
| Level 1     | 100            |
| Level 2     | 200            |
| Level 3     | 300            |
| Level 4     | 450            |
| Level 5     | 600            |
| Level 6     | 900            |
| Level 7     | 1200           |
| Level 8     | 1500           |
| Level 9     | 2000           |
| Level 10    | 2500           |
| Level 11    | 3000           |
| Level 12    | 3500           |
| Level 13    | 4000           |
| Level 14    | 4500           |
| Level 15    | 5000           |

### 9.3 전력 모드 전환 절차

#### Active → HIBERN8

```
호스트                              장치
  │── DME_HIBERNATE_ENTER.req ───→  │
  │  ←─ DME_HIBERNATE_ENTER.cnf ─   │  (확인)
  │  [M-PHY 링크 비활성화]           │
```

#### HIBERN8 → Active

```
호스트                              장치
  │── DME_HIBERNATE_EXIT.req ────→  │
  │  ←─ DME_HIBERNATE_EXIT.cnf ──   │  (링크 복원 완료)
  │  [고속 데이터 전송 재개]          │
```

### 9.4 Deep Sleep

Deep Sleep 모드는 HIBERN8보다 낮은 전력 소비를 달성하기 위해 장치 내부 회로의 일부를 추가로 비활성화한다. UFS 3.1에서 도입되었으며 UFS 5.0에서도 지원된다.

### 9.5 Auto-Hibernate

호스트가 설정한 타이머 값에 따라 일정 시간 동안 I/O 없을 시 자동으로 HIBERN8 진입한다.

- `bAutoHibernateTimer` 속성으로 타이머 설정 (단위: 1 ms)
- 값 0: Auto-Hibernate 비활성화

---

## 10. 보안 기능

### 10.1 RPMB (Replay Protected Memory Block)

RPMB는 단방향 카운터와 HMAC-SHA256을 사용하여 재생 공격을 방지하는 보안 영역이다.

#### RPMB 동작 원리

1. 호스트와 장치가 **인증 키(Authentication Key)**를 공유
2. 모든 RPMB 쓰기 요청에 **쓰기 카운터(Write Counter)** 포함
3. 장치는 카운터가 일치해야 쓰기 수행
4. HMAC-SHA256으로 요청 무결성 검증

#### RPMB 파티션

| 항목       | 설명                             |
| -------- | ------------------------------ |
| 최대 파티션 수 | 4개 (UFS 5.0)                   |
| 파티션 크기   | 128 KB 단위                      |
| 접근 방법    | SECURITY PROTOCOL IN/OUT 명령 사용 |

### 10.2 인라인 암호화 (Inline Encryption)

UFS 5.0은 장치 내부에서 데이터 암호화/복호화를 수행하는 인라인 암호화를 지원한다.

- **알고리즘**: AES-256-XTS (필수), AES-128-XTS (선택)
- **암호화 단위**: 논리 블록 단위 (512 B 또는 4096 B)
- **키 슬롯**: 호스트가 키 슬롯에 암호화 키 설정 후 I/O 명령과 함께 슬롯 번호 지정

### 10.3 쓰기 방지 (Write Protection)

| 유형          | 설명               |
| ----------- | ---------------- |
| 영구 쓰기 방지    | 비가역적, 제조 후 설정 가능 |
| 전원 인가 쓰기 방지 | 전원 차단 후 자동 해제    |
| 일시적 쓰기 방지   | 소프트웨어로 설정/해제 가능  |

---

## 11. 성능 특성

### 11.1 세대별 성능 비교

| 항목                 | UFS 3.1     | UFS 4.0     | UFS 5.0          |
| ------------------ | ----------- | ----------- | ---------------- |
| 최대 순차 읽기/쓰기        | ~2,100 MB/s | ~4,200 MB/s | **~10,800 MB/s** |
| 최대 랜덤 읽기 (4K IOPS) | ~100K IOPS  | ~200K IOPS  | 향상               |
| 최대 랜덤 쓰기 (4K IOPS) | ~70K IOPS   | ~150K IOPS  | 향상               |
| 최고 기어              | HS-G4 (NRZ) | HS-G5 (NRZ) | **HS-G6 (PAM4)** |
| 레인당 최대 속도          | 9.984 Gbps  | 23.2 Gbps   | **46.694 Gbps**  |
| x2 링크 최대 속도        | ~19.9 Gbps  | ~46.4 Gbps  | **~93.4 Gbps**   |
| 최대 큐 깊이            | 32          | 32          | 256              |

> 순차 읽기/쓰기 10.8 GB/s는 JEDEC 공식 발표 수치 (JESD220H, 2026.02). 랜덤 IOPS는 공식 스펙 미발표.

> 실제 성능은 장치 제조사, 낸드 플래시 유형(TLC/QLC), 동작 온도 등에 따라 상이하다.

### 11.2 Write Booster (WB)

Write Booster는 SLC 캐시 영역을 활용하여 쓰기 성능을 일시적으로 향상시키는 기능이다.

| 항목     | 설명                       |
| ------ | ------------------------ |
| 버퍼 크기  | 제조사 정의 (최대 수 GB)         |
| 버퍼 유형  | 공유 버퍼 또는 LUN별 전용 버퍼      |
| 플러시 정책 | 자동 또는 호스트 제어             |
| 활성화 방법 | `fWriteBoosterEn` 플래그 설정 |

#### WB 버퍼 수명 지시자

| bAvailableWBBufferSize 값   | 의미             |
| -------------------------- | -------------- |
| 0x00                       | 버퍼 소진 (0%)     |
| 0x01–0x0A                  | 가용 용량 10%–100% |

### 11.3 HPB (Host Performance Booster)

HPB는 호스트 DRAM에 낸드 플래시의 논리-물리 주소 변환 테이블(L2P Map) 일부를 캐싱하여 읽기 성능을 향상시키는 기능이다.

- 호스트가 장치로부터 L2P 맵 정보를 읽어 DRAM에 저장
- 읽기 명령 시 HPB READ 명령으로 물리 주소 힌트 제공
- 장치의 FTL(Flash Translation Layer) 조회 오버헤드 감소

### 11.4 컨텍스트 ID (Context ID)

UFS 5.0은 다중 컨텍스트(Context)를 지원하여 운영체제의 다른 프로세스/작업별로 독립적인 I/O 특성을 장치에 알릴 수 있다.

---

## 12. 디스크립터 및 레지스터

### 12.1 장치 디스크립터 (Device Descriptor)

| 필드                    | 오프셋      | 크기     | 설명                    |
| --------------------- | -------- | ------ | --------------------- |
| bLength               | 0x00     | 1      | 디스크립터 길이              |
| bDescriptorIDN        | 0x01     | 1      | 0x00 (Device)         |
| bDevice               | 0x02     | 1      | 장치 클래스 (0x00: UFS)    |
| bDeviceClass          | 0x03     | 1      | 서브클래스                 |
| bProtocol             | 0x04     | 1      | 프로토콜 버전               |
| bNumberLU             | 0x05     | 1      | 활성화된 LUN 수            |
| bNumberWLU            | 0x06     | 1      | Well-known LUN 수      |
| bBootEnable           | 0x07     | 1      | 부팅 LUN 활성화 여부         |
| bDescrAccessEn        | 0x08     | 1      | 디스크립터 접근 허용           |
| bInitPowerMode        | 0x09     | 1      | 초기 전력 모드              |
| bHighPriorityLUN      | 0x0A     | 1      | 고우선순위 LUN             |
| bSecureRemovalType    | 0x0B     | 1      | 보안 삭제 유형              |
| bSecurityLU           | 0x0C     | 1      | 보안 LUN 지원 여부          |
| bBackgroundOpsTermLat | 0x0D     | 1      | 백그라운드 작업 종료 지연        |
| bInitActiveICCLevel   | 0x0E     | 1      | 초기 전류 소비 등급           |
| wSpecVersion          | 0x10     | 2      | 규격 버전                 |
| wManufactureDate      | 0x12     | 2      | 제조 날짜                 |
| iManufacturerName     | 0x14     | 1      | 제조사명 인덱스              |
| iProductName          | 0x15     | 1      | 제품명 인덱스               |
| iSerialNumber         | 0x16     | 1      | 시리얼 번호 인덱스            |
| iOemID                | 0x17     | 1      | OEM ID 인덱스            |
| wManufacturerID       | 0x18     | 2      | 제조사 ID (JEDEC)        |
| bUD0BaseOffset        | 0x1A     | 1      | Unit Descriptor 0 오프셋 |
| bUDConfigPLength      | 0x1B     | 1      | Unit Descriptor 설정 길이 |
| bDeviceRTTCap         | 0x1C     | 1      | 최대 동시 RTT 수           |
| wPeriodicRTCUpdate    | 0x1D     | 2      | 주기적 RTC 갱신            |
| bUFSFeaturesSupport   | 0x1F     | 1      | 지원 기능 비트맵             |
| bFFUTimeout           | 0x20     | 1      | FFU 타임아웃              |
| bQueueDepth           | 0x21     | 1      | 최대 큐 깊이               |
| wDeviceVersion        | 0x24     | 2      | 장치 버전                 |
| bNumSecureWPArea      | 0x26     | 1      | 보안 쓰기 방지 영역 수         |
| dPSAMaxDataSize       | 0x27     | 4      | PSA 최대 데이터 크기         |
| bPSAStateTimeout      | 0x2B     | 1      | PSA 상태 타임아웃           |
| iProductRevisionLevel | 0x2C     | 1      | 제품 리비전 인덱스            |

### 12.2 지오메트리 디스크립터 (Geometry Descriptor)

| 필드                             | 오프셋      | 크기     | 설명                  |
| ------------------------------ | -------- | ------ | ------------------- |
| bLength                        | 0x00     | 1      | 디스크립터 길이            |
| bDescriptorIDN                 | 0x01     | 1      | 0x05 (Geometry)     |
| bMediaTechnology               | 0x02     | 1      | 미디어 기술 유형           |
| qTotalRawDeviceCapacity        | 0x04     | 8      | 전체 원시 용량 (512 B 섹터) |
| bMaxNumberLU                   | 0x0C     | 1      | 최대 LUN 수            |
| dSegmentSize                   | 0x0D     | 4      | 세그먼트 크기 (512 B 단위)  |
| bAllocationUnitSize            | 0x11     | 1      | 할당 단위 크기 (세그먼트 수)   |
| bMinAddrBlockSize              | 0x12     | 1      | 최소 주소 지정 블록 크기      |
| bOptimalReadBlockSize          | 0x13     | 1      | 최적 읽기 블록 크기         |
| bOptimalWriteBlockSize         | 0x14     | 1      | 최적 쓰기 블록 크기         |
| bMaxInBufferSize               | 0x15     | 1      | 최대 입력 버퍼 크기         |
| bMaxOutBufferSize              | 0x16     | 1      | 최대 출력 버퍼 크기         |
| bRPMB_ReadWriteSize            | 0x17     | 1      | RPMB 읽기/쓰기 크기       |
| bDynamicCapacityResourcePolicy | 0x18     | 1      | 동적 용량 정책            |
| bDataOrdering                  | 0x19     | 1      | 데이터 순서 지원           |
| bMaxContexIDNumber             | 0x1A     | 1      | 최대 컨텍스트 ID 수        |
| bSysDataTagUnitSize            | 0x1B     | 1      | 시스템 데이터 태그 단위       |
| bSysDataTagResSize             | 0x1C     | 1      | 시스템 데이터 태그 예약 크기    |
| bSupportedSecRTypes            | 0x1D     | 1      | 지원 보안 삭제 유형         |
| wSupportedMemoryTypes          | 0x1E     | 2      | 지원 메모리 유형 비트맵       |
| dSystemCodeMaxNAllocU          | 0x20     | 4      | 시스템 코드 최대 할당 단위     |
| wSystemCodeCapAdjFac           | 0x24     | 2      | 시스템 코드 용량 조정 계수     |
| dNonPersistMaxNAllocU          | 0x26     | 4      | 비영구 최대 할당 단위        |
| wNonPersistCapAdjFac           | 0x2A     | 2      | 비영구 용량 조정 계수        |

### 12.3 장치 건강 디스크립터 (Device Health Descriptor)

장치의 수명 정보를 제공한다.

| 필드                  | 오프셋      | 크기     | 설명                                    |
| ------------------- | -------- | ------ | ------------------------------------- |
| bLength             | 0x00     | 1      | 디스크립터 길이                              |
| bDescriptorIDN      | 0x01     | 1      | 0x07                                  |
| bPreEOLInfo         | 0x02     | 1      | 사전 EOL 상태 (01h: 정상, 02h: 경고, 03h: 긴급) |
| bDeviceLifeTimeEstA | 0x03     | 1      | 수명 추정 A (0%–90%+ 범위)                  |
| bDeviceLifeTimeEstB | 0x04     | 1      | 수명 추정 B                               |
| VendorPropInfo      | 0x05     | 32     | 제조사 정의 정보                             |

---

## 13. 오류 처리

### 13.1 UPIU 응답 코드 (Response Code)

| 코드     | 의미             |
| ------ | -------------- |
| 0x00   | Target Success |
| 0x01   | Target Failure |

### 13.2 Overall Command Status (OCS)

| OCS 값    | 의미                               |
| -------- | -------------------------------- |
| 0x00     | SUCCESS                          |
| 0x01     | INVALID_COMMAND_TABLE_ATTRIBUTES |
| 0x02     | INVALID_PRDT_ATTRIBUTES          |
| 0x03     | MISMATCH_DATA_BUFFER_SIZE        |
| 0x04     | MISMATCH_RESPONSE_UPIU_SIZE      |
| 0x05     | PEER_COMMUNICATION_FAILURE       |
| 0x06     | ABORTED                          |
| 0x07     | FATAL_ERROR                      |

### 13.3 SCSI 체크 조건 (Sense Data)

SCSI 명령 실패 시 장치는 Sense Data를 반환한다.

| Sense Key   | 의미                            |
| ----------- | ----------------------------- |
| 0x01        | RECOVERED ERROR               |
| 0x02        | NOT READY                     |
| 0x03        | MEDIUM ERROR (낸드 읽기 오류)       |
| 0x04        | HARDWARE ERROR                |
| 0x05        | ILLEGAL REQUEST (잘못된 명령/파라미터) |
| 0x06        | UNIT ATTENTION                |
| 0x07        | DATA PROTECT (쓰기 방지 위반)       |
| 0x0B        | ABORTED COMMAND               |

### 13.4 오류 복구 절차

1. **소프트 오류**: 장치 자체 ECC로 복구 (호스트에 투명하게 처리)
2. **정정 불가 오류**: MEDIUM ERROR Sense Key 반환
3. **링크 오류**: UniPro ARQ 재전송 또는 링크 재초기화
4. **작업 중단**: ABORT TASK 작업 관리 명령으로 명령 취소

---

## 14. UFS 5.0 주요 변경사항

UFS 4.0 대비 UFS 5.0에서 신규 도입·변경된 주요 사항은 다음과 같다.

### 14.1 성능 향상

| 항목       | 변경 내용                                                              |
| -------- | ------------------------------------------------------------------ |
| M-PHY 기어 | **HS-G6 + PAM4** 신규 추가 (23.2 Gbps NRZ → **46.694 Gbps** PAM4/lane) |
| 신호 방식    | NRZ(2레벨) → **PAM4(4레벨)** 전환, 심볼당 2비트 전송                            |
| 라인 인코딩   | 128b/132b → **1b1b** 신규 도입 (오버헤드 최대 20% 절감)                        |
| RS-FEC   | UniPro v3.0에서 RS-FEC 도입                                            |
| 큐 깊이     | 32 → **256**으로 확장                                                  |
| 순차 읽기/쓰기 | 최대 ~4,200 MB/s → **~10,800 MB/s**                                  |

### 14.2 전력 및 시스템 통합

JEDEC JESD220H에서 공식 발표된 UFS 5.0 전력/통합 개선사항:

| 항목           | 변경 내용                                                    |
| ------------ | -------------------------------------------------------- |
| **전용 전원 레일** | PHY와 메모리 서브시스템 간 **노이즈 격리**를 위한 별도 전원 레일 추가 (시스템 통합 단순화) |
| 링크 등화기 통합    | 신뢰성 있는 신호 무결성 보장 (M-PHY v6.0 선택적 기능과 연계)                 |

### 14.3 보안 강화

JEDEC JESD220H에서 공식 발표된 UFS 5.0 보안 개선사항:

| 항목                          | 변경 내용                                              |
| --------------------------- | -------------------------------------------------- |
| **인라인 해싱 (Inline Hashing)** | **스토리지 경로 내에서 직접 해시 연산** — 데이터 변조·손상을 빠르고 효율적으로 탐지 |
| 인라인 암호화                     | AES-256-XTS 지원 강화                                  |

### 14.4 규격 번호 요약 (공식 확인)

| 규격 번호                | 내용                                 | 비고            |
| -------------------- | ---------------------------------- | ------------- |
| **JESD220H**         | **UFS 5.0 메인 규격**                  | 2026.02.26 발행 |
| JESD220G             | UFS 4.1 메인 규격                      | 2024.12 발행    |
| JESD220F             | UFS 4.0 메인 규격                      | 2022.08 발행    |
| **JESD223G**         | **UFS 5.0 Flash Memory Interface** | 2026.02.26 발행 |
| **MIPI M-PHY v6.0**  | HS-G6 PAM4 물리 계층 규격                | 2026.02 발행    |
| **MIPI UniPro v3.0** | 데이터 링크·네트워크 계층 규격                  | 2026.02 발행    |

---

## 15. UFS 4.1 vs UFS 5.0 상세 비교

> **출처**: JEDEC 공식 보도자료 (2025.01 — JESD220G UFS 4.1 발표, 2026.02 — JESD220H UFS 5.0 발표)

### 15.1 UFS 4.1 개요

UFS 4.1(**JESD220G**)은 2024년 12월 JEDEC이 발행한 UFS 4.0의 마이너 리비전이다. **물리 인터페이스는 M-PHY v5.0 + UniPro v2.0으로 UFS 4.0과 동일하게 유지**되며, UFS 4.0 하드웨어와 완전히 호환된다. UFS 4.1이 개선한 내용은 물리 계층 성능이 아닌, **호스트-장치 협력 최적화 기능**이다.

JEDEC이 공식 발표한 UFS 4.1 신규 기능은 다음과 같다:

| 신규 기능                                             | 설명                                                           |
| ------------------------------------------------- | ------------------------------------------------------------ |
| **Host-Initiated Defragmentation (호스트 주도 조각 모음)** | 호스트가 읽기 트래픽 최적화를 위해 장치 내 데이터 재배치를 명시적으로 요청하는 메커니즘            |
| **Zoned UFS (ZUFS)**                              | 구역(Zone) 기반 스토리지 지원 — 쓰기 증폭(WAF) 감소 및 GC 부담 최소화              |
| **WriteBooster Buffer Resize & Partial Flush**    | 호스트가 WB 버퍼 크기 재설정, 데이터 피닝(Pinning), 부분 플러시를 요청하여 시스템 처리량 극대화 |
| **Permanent Bootable Logical Unit**               | 논리 유닛을 영구 부팅 가능 상태로 설정                                       |
| **Enhanced Exception Handling**                   | 예외 이벤트 처리 강화                                                 |

UFS 5.0(**JESD220H**)은 MIPI M-PHY v6.0 + UniPro v3.0을 채택하여 물리 계층부터 전면 업그레이드한 **메이저 리비전**이다.

---

### 15.2 물리 계층 비교

UFS 4.1은 UFS 4.0과 **동일한 M-PHY v5.0 + UniPro v2.0** 물리 인터페이스를 사용한다. UFS 5.0은 **M-PHY v6.0 + UniPro v3.0**으로 전환하여 물리 계층을 전면 교체했다. (출처: JEDEC 공식 보도자료)

| 항목        | UFS 4.1 (JESD220G)  | UFS 5.0 (JESD220H)   |
| --------- | ------------------- | -------------------- |
| M-PHY 버전  | **v5.0**            | **v6.0**             |
| UniPro 버전 | **v2.0**            | **v3.0**             |
| 최고 기어     | HS-G5 (NRZ)         | **HS-G6 (PAM4)**     |
| 레인당 최대 속도 | 23.2 Gbps           | **46.694 Gbps**      |
| 라인 인코딩    | 128b/132b           | **1b1b (신규)**        |
| RS-FEC    | 미적용                 | **UniPro v3.0에서 적용** |
| 링크 등화기    | 미적용                 | **M-PHY v6.0에서 선택적** |
| 지원 레인 수   | x1, x2              | x1, x2 (동일)          |

PAM4 도입으로 보 레이트는 HS-G5와 동일하게 유지하면서 심볼당 2비트를 인코딩하여 유효 데이터 전송률을 2배로 증가시켰다.

---

### 15.3 성능 비교 (공식 발표 수치 기준)

| 항목             | UFS 4.1     | UFS 5.0          | 근거                                |
| -------------- | ----------- | ---------------- | --------------------------------- |
| 최대 순차 읽기/쓰기    | ~4,200 MB/s | **~10,800 MB/s** | JEDEC JESD220H 공식 발표              |
| 최대 큐 깊이        | 32          | **256**          | JEDEC JESD220H                    |
| 링크 최대 대역폭 (x2) | ~46.4 Gbps  | **~93.4 Gbps**   | MIPI M-PHY v6.0 (46.694 Gbps × 2) |
| 랜덤 IOPS        | —           | —                | 공식 스펙 미발표                         |

---

### 15.4 UFS 4.1 신규 기능 (JEDEC 공식 발표)

UFS 4.1이 UFS 4.0 대비 추가한 기능 (출처: JEDEC 공식 보도자료, 2025.01):

| 기능                                             | 설명                                        |
| ---------------------------------------------- | ----------------------------------------- |
| **Host-Initiated Defragmentation**             | 호스트가 읽기 트래픽 최적화를 위해 데이터 재배치를 장치에 명시적으로 요청 |
| **Zoned UFS (ZUFS)**                           | 구역 기반 스토리지 — 장치 GC 부담 감소 및 WAF 최소화        |
| **WriteBooster Buffer Resize & Partial Flush** | WB 버퍼 크기 재설정, 데이터 피닝(Pinning), 부분 플러시     |
| **Permanent Bootable Logical Unit**            | 논리 유닛을 영구 부팅 가능 상태로 설정                    |
| **Enhanced Exception Handling**                | 예외 이벤트 처리 강화                              |

---

### 15.5 UFS 5.0 신규 기능 (JEDEC 공식 발표)

UFS 5.0이 UFS 4.1 대비 추가한 기능 (출처: JEDEC 공식 보도자료, 2026.02):

| 기능                               | 설명                                  |
| -------------------------------- | ----------------------------------- |
| **HS-G6 + PAM4**                 | M-PHY v6.0 채택, 10.8 GB/s 순차 성능      |
| **큐 깊이 256**                     | 32 → 256 확장                         |
| **Inline Hashing**               | 스토리지 경로 내에서 직접 해시 연산으로 데이터 변조·손상 탐지 |
| **Distinct Power Supply Rail**   | PHY와 메모리 서브시스템 간 별도 전원 레일로 노이즈 격리   |
| **Integrated Link Equalization** | 신뢰성 있는 신호 무결성 보장                    |

---

### 15.6 하위 호환성 (공식 확인)

JEDEC이 명시한 호환성:

| 항목                       | 내용                              |
| ------------------------ | ------------------------------- |
| UFS 5.0 장치 + UFS 4.x 호스트 | HS-G5(NRZ) 기어로 폴백하여 동작          |
| UFS 4.x 장치 + UFS 5.0 호스트 | HS-G5(NRZ) 기어로 동작               |
| 하드웨어 호환성                 | UFS 5.0은 UFS 4.x 하드웨어와 완전 호환 유지 |

---

### 15.7 전체 비교 요약 (공식 발표 기반)

| 분류     | 항목                | UFS 4.1     | UFS 5.0           | 출처               |
| ------ | ----------------- | ----------- | ----------------- | ---------------- |
| **규격** | JEDEC 번호          | JESD220G    | **JESD220H**      | JEDEC            |
| **규격** | 발행일               | 2024.12     | **2026.02.26**    | JEDEC            |
| **물리** | M-PHY             | v5.0        | **v6.0**          | JEDEC/MIPI       |
| **물리** | UniPro            | v2.0        | **v3.0**          | JEDEC/MIPI       |
| **물리** | 최고 기어             | HS-G5 (NRZ) | **HS-G6 (PAM4)**  | MIPI             |
| **물리** | 레인당 속도            | 23.2 Gbps   | **46.694 Gbps**   | MIPI             |
| **물리** | 라인 인코딩            | 128b/132b   | **1b1b**          | MIPI             |
| **물리** | RS-FEC            | 없음          | **있음**            | MIPI UniPro v3.0 |
| **성능** | 순차 읽기/쓰기          | ~4.2 GB/s   | **~10.8 GB/s**    | JEDEC            |
| **성능** | 큐 깊이              | 32          | **256**           | JEDEC            |
| **보안** | Inline Hashing    | 없음          | **있음**            | JEDEC            |
| **전력** | 전용 전원 레일          | 없음          | **있음**            | JEDEC            |
| **기능** | Host-Init. Defrag | 없음          | —                 | JEDEC (UFS 4.1)  |
| **기능** | ZUFS              | 있음          | 있음                | JEDEC            |
| **호환** | 하위 호환             | UFS 4.0 호환  | **UFS 4.x 완전 호환** | JEDEC            |

---

## 16. MIPI M-PHY v6.0 규격

> **출처**: MIPI Alliance 공식 보도자료 — "MIPI Alliance Releases UniPro v3.0 and M-PHY v6.0, Accelerating JEDEC UFS Performance for Edge AI in Mobile, PC and Automotive" (발행일: 2026년 2월)

### 16.1 개요

MIPI M-PHY(Mobile Physical Layer)는 MIPI Alliance가 제정한 모바일·임베디드 환경용 고속 직렬 물리 계층 규격이다. UFS를 비롯한 다양한 인터페이스의 물리 계층으로 사용된다.

**M-PHY v6.0**은 MIPI Alliance가 2026년 2월 발행한 최신 버전으로, UFS 5.0(JESD220H)의 물리 계층으로 채택되었다.

| 규격             | 최고 기어      | 신호 방식      | 연관 UFS      |
| -------------- | ---------- | ---------- | ----------- |
| M-PHY v4.x     | HS-G4      | NRZ        | UFS 3.x     |
| M-PHY v5.0     | HS-G5      | NRZ        | UFS 4.x     |
| **M-PHY v6.0** | **HS-G6**  | **PAM4**   | **UFS 5.0** |

---

### 16.2 M-PHY v6.0 핵심 신규 기능 (공식 발표 내용)

MIPI Alliance가 공식적으로 발표한 M-PHY v6.0의 신규 기능:

#### 16.2.1 HS-G6 with PAM4

- 새로운 고속 기어 **HS-G6**를 PAM4(4-레벨 펄스 진폭 변조) 신호 방식으로 도입
- 레인당 최대 속도: **46.694 Gbps**
- HS-G5(NRZ, 23.2 Gbps/lane) 대비 동일 보 레이트에서 **대역폭 2배** 달성

PAM4는 신호 레벨을 4단계(V0~V3)로 확장하여 심볼당 2비트를 전송한다. NRZ(2레벨, 심볼당 1비트)와 비교하면 동일한 물리적 채널·클록에서 2배의 데이터를 전송할 수 있다.

```
NRZ (HS-G5):  레벨 1 ──  (1)
              레벨 0 ──  (0)      심볼당 1비트

PAM4 (HS-G6): 레벨 3 ──  (11)
              레벨 2 ──  (10)
              레벨 1 ──  (01)     심볼당 2비트
              레벨 0 ──  (00)
```

#### 16.2.2 1b1b 라인 인코딩 (신규)

- HS-G6에 **새로운 1b1b 라인 인코딩** 도입
- **8b10b 대비 PHY 코딩 오버헤드를 크게 절감**하여 처리 효율 향상
- DC 밸런스와 클록 복원은 스크램블링·프리코딩·그레이 코딩으로 처리

| 인코딩       | 오버헤드      | 특징                               |
| --------- | --------- | -------------------------------- |
| 8b/10b    | 20%       | 구형 방식                            |
| 128b/132b | ~3%       | HS-G4~G5 사용                      |
| **1b1b**  | **최소화**   | **HS-G6 신규, 8b10b 대비 최대 20% 개선** |

#### 16.2.3 링크 등화기 및 트레이닝 (선택적)

- **선택적(Optional)** 링크 등화기 및 트레이닝 기능 제공
- 더 높은 성능 마진과 향상된 상호운용성(Interoperability) 실현
- 구현 여부는 설계자 선택 사항

#### 16.2.4 하위 호환성

- M-PHY v5.0과 **하위 호환** 유지
- HS-G6을 지원하지 않는 장치와 연결 시 자동으로 이전 기어로 폴백

---

### 16.3 M-PHY v5.0 vs v6.0 비교 요약

| 항목             | M-PHY v5.0   | M-PHY v6.0      |
| -------------- | ------------ | --------------- |
| 최고 기어          | HS-G5        | **HS-G6**       |
| 신호 방식          | NRZ (2레벨)    | **PAM4 (4레벨)**  |
| 레인당 최대 속도      | 23.2 Gbps    | **46.694 Gbps** |
| 라인 인코딩 (최고 기어) | 128b/132b    | **1b1b**        |
| 링크 등화기         | 없음           | **선택적 지원**      |
| 하위 호환성         | —            | **v5.0 이하 호환**  |

---

### 16.4 PAM4의 신호 특성

PAM4는 NRZ 대비 Eye 개구부(Eye Opening)가 1/3로 줄어든다. 이에 따라 SNR(신호 대 잡음비) 요구가 증가하며, UniPro v3.0에서 RS-FEC를 도입하여 이를 보상한다. 등화기(Equalizer) 적용은 M-PHY v6.0에서 선택적으로 지원한다.

```
NRZ Eye (HS-G5):      PAM4 Eye ×3 (HS-G6):
                       ━━━━  레벨 3
  ████████              ↕ Eye 2
━━━━━━━━━━━━━         ━━━━  레벨 2
  ████████              ↕ Eye 1
                       ━━━━  레벨 1
━━━━━━━━━━━━━          ↕ Eye 0
                       ━━━━  레벨 0

Eye 높이 = 전체 신폭   Eye 높이 = 전체 신폭/3
```

---

## 17. MIPI UniPro v3.0 규격

> **출처**: MIPI Alliance 공식 보도자료 — "MIPI Alliance Releases UniPro v3.0 and M-PHY v6.0, Accelerating JEDEC UFS Performance for Edge AI in Mobile, PC and Automotive" (발행일: 2026년 2월)

### 17.1 개요

MIPI UniPro(Unified Protocol)는 M-PHY 위에서 동작하는 데이터 링크·네트워크 계층 규격이다. **UniPro v3.0**은 MIPI Alliance가 2026년 2월 발행한 최신 버전으로, M-PHY v6.0(HS-G6, PAM4)을 지원하고 UFS 5.0(JESD220H)의 데이터 링크 계층으로 채택되었다.

| 규격              | 최고 속도 지원                   | 연관 UFS      |
| --------------- | -------------------------- | ----------- |
| UniPro v2.0     | HS-G5 (23.2 Gbps/lane)     | UFS 4.x     |
| **UniPro v3.0** | **HS-G6 (46.6 Gbps/lane)** | **UFS 5.0** |

---

### 17.2 UniPro v3.0 핵심 신규 기능 (공식 발표 내용)

MIPI Alliance가 공식적으로 발표한 UniPro v3.0의 신규 기능:

#### 17.2.1 HS-G6 지원

- M-PHY v6.0 **HS-G6** 기반, 레인당 최대 **46.6 Gbps** 지원

#### 17.2.2 1b1b 라인 인코딩 도입

- **새로운 1b1b 인코딩 방식** 채택
- **8b10b 대비 시그널링 오버헤드를 최대 20% 절감**
- 1b1b 인코딩을 지원하기 위한 다음 부가 기능 추가:
  - **TFS 데이터 스크램블링(Scrambling)** — DC 밸런스 유지
  - **블록 코딩(Block Coding)** — 동기화 지원
  - **레인 정렬(Lane Alignment)** — 멀티레인 정렬
  - **그레이 코딩(Gray Coding)** — PAM4 심볼 오류 최소화
  - **프리코딩(Precoding)** — DFE 등화기 성능 향상 지원

#### 17.2.3 새로운 Transport Framing Structure (TFS)

- **새로운 TFS(전송 프레이밍 구조)** 도입
- 상위 내용의 스크램블링·블록 코딩·레인 정렬·그레이 코딩·프리코딩은 모두 이 TFS와 연계

#### 17.2.4 RS-FEC (Reed-Solomon Forward Error Correction)

- **RS-FEC** 도입으로 PAM4의 신호 품질 저하(SNR 감소) 보상
- FEC 적용 후 BER: **10⁻⁶** 수준 달성

#### 17.2.5 64비트 CRC

- 데이터 무결성 검사를 위한 **64비트 CRC** 도입
- RS-FEC + 64비트 CRC 조합으로 응용 계층에서 **BER < 10⁻²²** 달성

#### 17.2.6 링크 등화기 트레이닝 절차

- 응용 계층이 **최적 TX 등화 설정을 파악**할 수 있도록 링크 등화기 트레이닝 절차 추가
- M-PHY v6.0의 선택적 등화기 기능과 연계

#### 17.2.7 고속 링크 시작 의무화

- M-PHY **HS-G1 Rate A를 이용한 고속 링크 시작(High-Speed Link Start-Up)** 의무화
- 링크 시작 레이턴시 단축 효과

#### 17.2.8 하위 호환성

- UniPro **v2.0과 하위 호환** 유지

---

### 17.3 UniPro v2.0 vs v3.0 비교 요약

| 항목             | UniPro v2.0   | UniPro v3.0              |
| -------------- | ------------- | ------------------------ |
| 최고 M-PHY 기어 지원 | HS-G5         | **HS-G6**                |
| 레인당 최대 속도      | 23.2 Gbps     | **46.6 Gbps**            |
| 라인 인코딩         | 128b/132b     | **1b1b**                 |
| RS-FEC         | 없음            | **있음**                   |
| CRC            | CRC (이전 방식)   | **64비트 CRC**             |
| TFS 스크램블링      | 없음            | **있음**                   |
| 그레이 코딩         | 없음            | **있음**                   |
| 프리코딩           | 없음            | **있음**                   |
| 레인 정렬          | 없음            | **있음**                   |
| 링크 등화기 트레이닝    | 없음            | **있음**                   |
| 고속 링크 시작       | 선택적           | **의무화 (HS-G1 Rate A)**   |
| BER (응용 계층)    | —             | **< 10⁻²²** (FEC+CRC 결합) |
| 하위 호환성         | —             | **v2.0 호환**              |

---

### 17.4 BER 달성 구조

UniPro v3.0에서 RS-FEC와 64비트 CRC를 조합하여 얻는 BER 목표:

```
M-PHY v6.0 HS-G6 PAM4
   ↓ 물리 신호 수신
RS-FEC 적용 후 BER: ~10⁻⁶
   ↓
64비트 CRC 검증
   ↓
응용 계층(UFS) 도달 BER: < 10⁻²²
```

---

### 17.5 UFS 5.0 전체 스택 연계

```
┌─────────────────────────────────────────────┐
│  UFS 5.0 (JESD220H)                          │
│  UAP / UTP — 큐 깊이 256, Inline Hashing     │
├─────────────────────────────────────────────┤
│  MIPI UniPro v3.0                            │
│  TFS, 1b1b, RS-FEC, 64비트 CRC              │
│  링크 등화기 트레이닝, HS-G1 Rate A 의무화   │
├─────────────────────────────────────────────┤
│  MIPI M-PHY v6.0                            │
│  HS-G6, PAM4, 46.694 Gbps/lane             │
│  1b1b 인코딩, 선택적 링크 등화기             │
└─────────────────────────────────────────────┘
  ↕ 하위 호환 (HS-G5 이하 NRZ로 자동 폴백)
```


## 18. Integrated Link Equalization 상세 해설

> **출처**: JEDEC JESD220H (UFS 5.0), MIPI M-PHY v6.0 공식 규격, MIPI UniPro v3.0 공식 규격, MIPI Alliance 공식 보도자료 (2026년 2월)

---

### 18.1 개념 정의 (공식 표현)

각 규격이 공식적으로 서술하는 표현:

| 규격             | 공식 표현                                                                                  |
| -------------- | -------------------------------------------------------------------------------------- |
| JEDEC UFS 5.0  | "enhanced signal integrity through **integrated link equalization**"                   |
| MIPI M-PHY v6.0 | "**optional** link equalization and training feature to enable greater performance margin and enhanced interoperability" |
| MIPI UniPro v3.0 | "introduction of a **link equalization training procedure** to help the application layer identify optimal Tx equalization settings" |

**Integrated Link Equalization**은 UFS 5.0이 HS-G6(PAM4, 46.694 Gbps/lane)에서 신호 무결성(Signal Integrity)을 확보하기 위해 M-PHY v6.0의 선택적 등화기 하드웨어와 UniPro v3.0의 등화기 트레이닝 절차를 통합 적용하는 구조를 가리킨다.

---

### 18.2 등화(Equalization)가 필요한 이유

#### 18.2.1 PAM4 Eye 열화

PAM4는 동일한 보레이트(Baud Rate)에서 NRZ 대비 2배의 데이터를 전송하지만, 4-레벨 신호로 인해 Eye 높이가 NRZ의 **1/3**로 줄어든다.

```
NRZ Eye (HS-G5):            PAM4 Eye ×3 (HS-G6):

  ████████                   ━━━━  레벨 3
━━━━━━━━━━━━━                 ↕ Eye 2 (1/3)
  ████████                   ━━━━  레벨 2
                              ↕ Eye 1 (1/3)
                             ━━━━  레벨 1
━━━━━━━━━━━━━                 ↕ Eye 0 (1/3)
                             ━━━━  레벨 0

Eye 높이 = 전체 신폭            Eye 높이 = 전체 신폭/3
```

- Eye 높이가 1/3으로 감소 → 노이즈·지터 허용 마진이 크게 줄어듦
- SNR(신호 대 잡음비) 요구가 NRZ 대비 큰 폭으로 증가

#### 18.2.2 고주파 채널 손실 (Channel Loss)

HS-G6의 보레이트는 HS-G5 대비 2배이므로, 채널(PCB 배선, 커넥터, 패키지)에서 발생하는 고주파 손실이 크게 증가한다.

- 채널 손실 특성: 주파수가 높을수록 손실이 증가 (skin effect, dielectric loss)
- 손실이 크면 수신 신호 파형이 뭉개져 Eye가 추가로 닫힘

#### 18.2.3 ISI (Inter-Symbol Interference, 심볼 간 간섭)

고속 신호에서 이전 심볼이 현재 심볼에 영향을 주는 ISI가 심화된다.

- ISI는 Eye를 수직(높이)·수평(너비) 양방향으로 닫는다
- PAM4 환경에서는 NRZ보다 ISI에 대한 민감도가 높다

---

### 18.3 등화기 구성 요소

공식 규격은 구체적인 등화기 탭 수나 파라미터 수치를 공개하지 않는다. 아래는 고속 직렬 인터페이스에서 일반적으로 사용하는 등화기 유형과 그 역할이다.

#### 18.3.1 TX FFE (Feed-Forward Equalization, 송신 전치 등화)

- 송신단에서 신호를 전송하기 **전에** 채널의 주파수 응답을 역보상(pre-emphasis)
- 고주파 성분을 미리 강조하여 채널 통과 후 파형을 평탄하게 함
- **UniPro v3.0 트레이닝 절차의 주요 제어 대상**: "응용 계층이 최적 TX 등화 설정을 파악"

#### 18.3.2 RX CTLE (Continuous Time Linear Equalizer, 수신 아날로그 등화)

- 수신단 아날로그 회로에서 채널 손실을 주파수 영역에서 보상
- 고주파 이득을 높여 손실된 신호 성분 복원

#### 18.3.3 RX DFE (Decision Feedback Equalizer, 결정 궤환 등화)

- 수신단에서 이전에 결정(슬라이싱)된 심볼을 피드백으로 활용하여 ISI를 디지털적으로 제거
- **UniPro v3.0 프리코딩(Precoding)**: DFE 성능을 향상시키기 위해 1b1b 인코딩 체계에 포함됨

---

### 18.4 Integrated Link Equalization의 두 축

UFS 5.0의 "통합(Integrated)" 구조는 다음 두 계층이 역할을 분담하는 방식이다.

```
┌──────────────────────────────────────────────────────────┐
│  MIPI UniPro v3.0 (링크 계층)                             │
│  • 링크 등화기 트레이닝 절차(프로토콜)                     │
│  • 응용 계층이 최적 TX FFE 설정을 파악하도록 지원          │
│  • 프리코딩(Precoding) — DFE 성능 향상 지원               │
├──────────────────────────────────────────────────────────┤
│  MIPI M-PHY v6.0 (물리 계층)                              │
│  • 선택적(Optional) 등화기 하드웨어 (TX FFE / RX CTLE 등) │
│  • 성능 마진 확대 및 상호운용성 향상 목적                  │
└──────────────────────────────────────────────────────────┘
```

| 역할                    | 담당 규격         | 내용                                           |
| --------------------- | ------------- | -------------------------------------------- |
| 등화기 하드웨어(선택적)         | M-PHY v6.0   | TX FFE, RX CTLE 등 물리 등화기 회로                 |
| 등화기 트레이닝 프로토콜         | UniPro v3.0  | 응용 계층이 최적 TX 등화 설정을 결정하는 절차                 |
| 등화기 성능 향상 지원 (인코딩)    | UniPro v3.0  | 프리코딩(Precoding)으로 DFE 오류 전파 방지               |
| 통합 적용 선언              | UFS 5.0      | "integrated link equalization" 으로 신호 무결성 확보  |

---

### 18.5 트레이닝 절차 개요 (UniPro v3.0 공식 내용 기반)

MIPI UniPro v3.0은 **링크 등화기 트레이닝 절차**를 공식적으로 정의한다. 공식 발표에 명시된 내용:

> "introduction of a link equalization training procedure to help the application layer identify optimal Tx equalization settings"

즉, 트레이닝의 목적은 **최적 TX 등화 설정 파악**이다. 구체적 절차 단계(Step-by-Step)는 공식 유료 규격에 수록되어 있어 아래에는 원칙만 기재한다.

**트레이닝의 일반 원리:**

1. 송신단이 특정 TX FFE 설정으로 트레이닝 패턴 전송
2. 수신단이 Eye 마진(BER, 신호 품질) 측정
3. 측정 결과를 링크 프로토콜을 통해 응용 계층에 전달
4. 응용 계층이 최적 설정을 결정하여 TX FFE 적용
5. 반복 수렴 후 트레이닝 완료, 데이터 전송 시작

---

### 18.6 Integrated Link Equalization과 RS-FEC의 관계

Integrated Link Equalization과 RS-FEC는 서로 **보완적** 역할을 한다.

```
물리 채널
   │
   ▼
[등화기 (M-PHY v6.0 선택적)]
   │  채널 손실·ISI 보상 → Eye 개선
   ▼
[RS-FEC (UniPro v3.0)]
   │  잔여 비트 오류 정정 → BER ~10⁻⁶ 달성
   ▼
[64비트 CRC (UniPro v3.0)]
   │  데이터 무결성 검증
   ▼
응용 계층 BER < 10⁻²²
```

| 기능                  | 역할                                | 적용 위치        |
| ------------------- | --------------------------------- | ------------ |
| TX FFE / RX CTLE    | 채널 손실·ISI 보상 (하드웨어)              | M-PHY v6.0  |
| 프리코딩                | DFE 오류 전파 방지 (인코딩)               | UniPro v3.0 |
| RS-FEC              | 잔여 비트 오류 정정                       | UniPro v3.0 |
| 64비트 CRC            | 최종 데이터 무결성 검증                    | UniPro v3.0 |
| **결합 효과**           | **응용 계층 BER < 10⁻²²**            | UFS 5.0     |

---

### 18.7 "선택적(Optional)" 적용의 의미

M-PHY v6.0은 링크 등화기를 **선택적(Optional)**으로 정의한다. 이는:

- 등화기 하드웨어 구현 여부는 칩 설계사(fabless/IDM)의 선택
- 등화기를 구현하지 않아도 HS-G6 동작은 가능하나, 채널 손실이 큰 환경에서는 성능 마진 감소
- UniPro v3.0의 트레이닝 절차는 등화기가 구현된 장치에서만 의미 있음
- 등화기 미구현 장치 간 연결 시에도 RS-FEC·64비트 CRC는 여전히 동작

**MIPI 공식 표현**: "optional link equalization and training feature to enable **greater performance margin** and **enhanced interoperability**"

→ 등화기는 필수(Mandatory)가 아닌 성능 마진·상호운용성 향상을 위한 선택적 강화 기능이다.

---

### 18.8 요약

| 항목         | 내용                                                        |
| ---------- | --------------------------------------------------------- |
| 정식 명칭      | Integrated Link Equalization (통합 링크 등화)                   |
| UFS 5.0 선언 | "enhanced signal integrity through integrated link equalization" |
| 물리 계층 역할   | M-PHY v6.0 — 선택적 등화기 하드웨어 (TX FFE, RX CTLE 등)           |
| 링크 계층 역할   | UniPro v3.0 — 링크 등화기 트레이닝 절차 (최적 TX 설정 파악)              |
| 필요 이유      | PAM4 Eye 1/3 감소 + HS-G6 고주파 채널 손실 + ISI 증가              |
| 연계 기능      | 프리코딩(Precoding), RS-FEC, 64비트 CRC                        |
| 최종 BER 목표  | < 10⁻²² (응용 계층, RS-FEC + 64비트 CRC 조합)                   |
| 등화기 의무 여부  | **선택적(Optional)** — M-PHY v6.0 공식 표현                     |

---

## 참고 문헌

### 공식 규격 문서

1. JEDEC Standard **JESD220H** — *Universal Flash Storage (UFS) Version 5.0*, 2026.02.26
2. JEDEC Standard **JESD220G** — *Universal Flash Storage (UFS) Version 4.1*, 2024.12
3. JEDEC Standard **JESD220F** — *Universal Flash Storage (UFS) Version 4.0*, 2022.08
4. JEDEC Standard **JESD223G** — *UFS Flash Memory Interface*, 2026.02.26
5. MIPI Alliance Specification — *M-PHY, Version 6.0*, 2026.02
6. MIPI Alliance Specification — *UniPro, Version 3.0*, 2026.02

### 공식 보도자료 (본 문서 작성 근거)

7. JEDEC 공식 보도자료 — *"JEDEC® Announces Updates to Universal Flash Storage (UFS) and Memory Interface Standards"*, 2025.01 (UFS 4.1 발표)
8. JEDEC 공식 보도자료 — *"JEDEC UFS 5.0 Standard to Deliver Sequential Performance up to 10.8 GB/s"*, 2026.02
9. MIPI Alliance 공식 보도자료 — *"MIPI Alliance Releases UniPro v3.0 and M-PHY v6.0, Accelerating JEDEC UFS Performance for Edge AI in Mobile, PC and Automotive"*, 2026.02

---

*본 문서의 섹션 1~14는 JEDEC UFS 공개 기술 자료 기반이며, 섹션 15~17(UFS 4.1 비교, M-PHY v6.0, UniPro v3.0)은 위 공식 보도자료에 명시된 내용만을 기재했습니다. 공식 규격 원문은 JEDEC(www.jedec.org) 및 MIPI Alliance(www.mipi.org) 공식 웹사이트에서 구입하시기 바랍니다.*
