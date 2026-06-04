# JEDEC UFS 5.0 규격 한국어 번역 요약

> **출처**: JEDEC JESD220F — Universal Flash Storage (UFS) Version 5.0  
> **원본 언어**: 영어 → **번역 언어**: 한국어  
> **작성 기준**: JEDEC 공개 자료 및 MIPI Alliance 규격 문서 기반

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

---

## 1. 소개

### 1.1 개요

UFS(Universal Flash Storage)는 JEDEC(Joint Electron Device Engineering Council)에서 제정한 플래시 메모리 인터페이스 표준이다. 스마트폰, 태블릿, 자동차용 전자기기, 서버, IoT 기기 등 다양한 분야에서 고성능 낸드 플래시 스토리지 인터페이스로 사용된다.

UFS 5.0(JESD220F)은 UFS 4.0(JESD220E) 이후의 차세대 규격으로, 다음과 같은 목표를 지향한다:

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

| 약어 | 영문 전체 | 한국어 의미 |
|------|-----------|------------|
| UFS | Universal Flash Storage | 범용 플래시 스토리지 |
| M-PHY | Mobile Physical Layer | 모바일 물리 계층 |
| UniPro | Unified Protocol | 통합 프로토콜 |
| UTP | UFS Transport Protocol | UFS 전송 프로토콜 |
| UAP | UFS Application Protocol | UFS 응용 프로토콜 |
| UCS | UFS Command Set | UFS 명령어 집합 |
| UPIU | UFS Protocol Information Unit | UFS 프로토콜 정보 단위 |
| LUN | Logical Unit Number | 논리 유닛 번호 |
| CDB | Command Descriptor Block | 명령어 기술자 블록 |
| PRDT | Physical Region Descriptor Table | 물리 영역 기술자 테이블 |
| RPMB | Replay Protected Memory Block | 재생 방지 메모리 블록 |
| HPB | Host Performance Booster | 호스트 성능 향상 |
| WB | Write Booster | 쓰기 향상 |
| TW | Turbo Write | 터보 쓰기 (WB의 구 명칭) |
| UIC | UFS Interconnect | UFS 상호연결 계층 |
| TMF | Task Management Function | 작업 관리 기능 |
| OCS | Overall Command Status | 전체 명령어 상태 |
| JEDEC | Joint Electron Device Engineering Council | 반도체 공학 표준화 기관 |
| JESD | JEDEC Standard | JEDEC 표준 번호 |
| HS | High Speed | 고속 모드 |
| PWM | Pulse Width Modulation | 펄스 폭 변조 (저전력 모드) |
| PAM4 | Pulse Amplitude Modulation 4-level | 4레벨 펄스 진폭 변조 (UFS 5.0 신규) |
| NRZ | Non-Return-to-Zero | 비귀환 제로 (기존 2레벨 신호 방식) |
| SLC | Single Level Cell | 단일 레벨 셀 |
| MLC | Multi Level Cell | 다중 레벨 셀 |
| TLC | Triple Level Cell | 3단 레벨 셀 |
| QLC | Quad Level Cell | 4단 레벨 셀 |

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

| 구성 | 설명 |
|------|------|
| x1 | 단일 레인 (TX 1개, RX 1개) |
| x2 | 듀얼 레인 (TX 2개, RX 2개), 최대 성능 |

### 3.3 논리 유닛 (LUN)

UFS 장치는 최대 **32개의 논리 유닛**을 지원한다.

| LUN 유형 | 설명 |
|----------|------|
| 일반 LUN (LUN 0–7) | 사용자 데이터 저장 영역 |
| Well-known LUN | 특수 목적 LUN (아래 표 참조) |

**Well-known LUN 목록:**

| Well-known LUN | 주소 | 용도 |
|----------------|------|------|
| W-LUN REPORT LUNS | 0xC1 | 지원 LUN 목록 조회 |
| W-LUN UFS DEVICE | 0xC0 | 장치 전체 제어 |
| W-LUN BOOT | 0xB0 | 부팅 파티션 |
| W-LUN RPMB | 0xC4 | 보안 재생방지 메모리 블록 |

---

## 4. 물리 계층 (M-PHY)

### 4.1 개요

UFS의 물리 계층은 MIPI Alliance의 **M-PHY 규격**을 따른다. M-PHY는 차동 신호 방식의 직렬 인터페이스로, 고속 모드(HS)와 저속 모드(PWM)를 모두 지원한다.

**UFS 5.0의 핵심 변경**: 기존 NRZ(2레벨) 신호 방식에서 **PAM4(4레벨 펄스 진폭 변조)** 방식으로 전환하여 동일한 보 레이트(Baud Rate)에서 데이터 전송률을 2배로 증가시켰다. PAM4는 심볼 하나당 2비트를 인코딩하므로, 같은 물리적 신호 속도에서 2배의 대역폭을 달성한다.

### 4.2 동작 모드

#### 4.2.1 고속(HS) 모드

HS 모드는 **Burst Mode**로 동작하며, 고속 데이터 전송에 사용된다.

| 기어 (Gear) | 신호 방식 | 레인당 속도 | x1 최대 속도 | x2 최대 속도 | 도입 버전 |
|-------------|----------|-------------|-------------|-------------|----------|
| HS-G1 | NRZ | 1.248 Gbps | ~150 MB/s | ~300 MB/s | UFS 1.0 |
| HS-G2 | NRZ | 2.496 Gbps | ~300 MB/s | ~600 MB/s | UFS 1.0 |
| HS-G3 | NRZ | 4.992 Gbps | ~600 MB/s | ~1,200 MB/s | UFS 2.0 |
| HS-G4 | NRZ | 9.984 Gbps | ~1,200 MB/s | ~2,900 MB/s | UFS 3.0 |
| HS-G5 | NRZ | 23.2 Gbps | ~2,900 MB/s | ~5,800 MB/s | UFS 4.0 |
| **HS-G6** | **PAM4** | **46.4 Gbps** | **~5,800 MB/s** | **~11,600 MB/s** | **UFS 5.0** |

> **UFS 5.0 핵심**: **HS-G6 + PAM4** 도입으로 레인당 최대 46.4 Gbps 달성. HS-G5 대비 동일 보 레이트에서 PAM4를 적용해 유효 대역폭 2배 증가.

#### 4.2.2 저속(PWM) 모드

PWM 모드는 초기화, 저전력 연결 유지에 사용된다.

| 기어 | 속도 |
|------|------|
| PWM-G1 | 3 Mbps |
| PWM-G2 | 6 Mbps |
| PWM-G3 | 12 Mbps |
| PWM-G4 | 24 Mbps |
| PWM-G5 | 48 Mbps |
| PWM-G6 | 96 Mbps |
| PWM-G7 | 192 Mbps |

### 4.3 직렬화 및 역직렬화 (SerDes)

M-PHY는 **8b/10b** 또는 **128b/132b** 인코딩을 사용하여 DC 밸런스와 클록 복원을 지원한다. HS-G4 이상에서는 128b/132b 인코딩이 적용된다.

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

| 항목 | 내용 |
|------|------|
| **장점** | 동일 보 레이트에서 2배 데이터 전송률, 주파수 대역폭 불변 |
| **단점** | 신호 레벨 간격 감소 → SNR(신호 대 잡음비) 요구 증가, DSP 기반 등화기(Equalizer) 필수 |
| **FEC 요구** | 신호 품질 저하 보완을 위해 **FEC(Forward Error Correction)** 필수 적용 |
| **EQ 복잡도** | CTLE(연속시간 선형 등화기) + DFE(결정 피드백 등화기) + FFE(전방향 피드등화기) 조합 사용 |

#### 4.4.3 PAM4와 FEC

PAM4는 NRZ 대비 심볼 간 레벨 차이가 1/3로 줄어 비트 오류율(BER)이 높아진다. 이를 보상하기 위해 UFS 5.0은 **RS(Reed-Solomon) FEC** 등 전방향 오류 정정을 M-PHY 계층에서 처리한다.

### 4.5 신호 레벨

| 파라미터 | NRZ (HS-G1~G5) | PAM4 (HS-G6) |
|----------|----------------|--------------|
| 차동 신호 진폭 | 200 mVpp (typ) | 200 mVpp (full scale, 레벨 간격 ~67 mVpp) |
| 공통 모드 전압 | 0~0.7 V | 0~0.7 V |
| 신호 임피던스 | 50 Ω (단종단), 100 Ω (차동) | 50 Ω (단종단), 100 Ω (차동) |
| 신호 레벨 수 | 2 (0, 1) | 4 (0, 1, 2, 3) |

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

| 기능 | 설명 |
|------|------|
| CRC | 각 프레임에 CRC 추가하여 비트 오류 감지 |
| ARQ | 오류 감지 시 재전송 요청 (NAK 기반) |
| FC_PDU 타이머 | 흐름 제어 타임아웃 감지 |

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

| Transaction Code | 유형 | 설명 |
|-----------------|------|------|
| 0x01 | Command UPIU | 호스트 → 장치, SCSI 명령 전송 |
| 0x21 | Response UPIU | 장치 → 호스트, 명령 완료 응답 |
| 0x02 | Data-Out UPIU | 호스트 → 장치, 쓰기 데이터 전송 |
| 0x22 | Data-In UPIU | 장치 → 호스트, 읽기 데이터 반환 |
| 0x04 | Task Management Request UPIU | 작업 관리 요청 |
| 0x24 | Task Management Response UPIU | 작업 관리 응답 |
| 0x16 | Query Request UPIU | 디스크립터/플래그/속성 조회·설정 |
| 0x36 | Query Response UPIU | 조회·설정 응답 |
| 0x1F | NOP Out UPIU | 링크 연결 확인 (호스트 → 장치) |
| 0x3F | NOP In UPIU | 링크 연결 확인 응답 (장치 → 호스트) |
| 0x05 | Ready-to-Transfer UPIU | 장치 준비 완료 신호 |
| 0x06 | Reject UPIU | 요청 거부 |

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

| 항목 | UFS 3.1 | UFS 4.0 | UFS 5.0 |
|------|---------|---------|---------|
| 최대 큐 깊이 | 32 | 32 | 256 |

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

| 코드 | 기능 |
|------|------|
| 0x01 | Read Descriptor |
| 0x02 | Write Descriptor |
| 0x03 | Read Attribute |
| 0x04 | Write Attribute |
| 0x05 | Read Flag |
| 0x06 | Set Flag |
| 0x07 | Clear Flag |
| 0x08 | Toggle Flag |

### 7.3 디스크립터 (Descriptors)

디스크립터는 장치 특성을 기술하는 읽기 전용(또는 일부 쓰기 가능) 데이터 구조이다.

| 디스크립터 IDN | 이름 | 주요 내용 |
|---------------|------|----------|
| 0x00 | Device Descriptor | 장치 유형, 버전, 제조사 |
| 0x01 | Configuration Descriptor | LUN 설정, 부팅 설정 |
| 0x02 | Unit Descriptor | 개별 LUN 크기, 속성 |
| 0x03 | Interconnect Descriptor | 지원 UniPro/M-PHY 버전 |
| 0x04 | String Descriptor | 제조사명, 제품명, 시리얼 번호 |
| 0x05 | Geometry Descriptor | 용량, 블록 크기, 할당 유닛 |
| 0x06 | Power Descriptor | 지원 전력 모드, 소비 전류 |
| 0x07 | Device Health Descriptor | 수명, 사전 EOL 경고 |
| 0x09 | Extended UFS Features Support Descriptor | UFS 5.0 확장 기능 지원 여부 |

### 7.4 플래그 (Flags)

| 플래그 IDN | 이름 | 설명 |
|-----------|------|------|
| 0x01 | fDeviceInit | 장치 초기화 트리거 |
| 0x04 | fPermanentWPEn | 영구 쓰기 방지 활성화 |
| 0x08 | fPowerOnWPEn | 전원 인가 쓰기 방지 |
| 0x0D | fWriteBoosterEn | Write Booster 활성화 |
| 0x0E | fWBBufferFlushEn | WB 버퍼 플러시 활성화 |
| 0x0F | fHPBEn | HPB 활성화 |

### 7.5 속성 (Attributes)

| 속성 IDN | 이름 | 설명 |
|---------|------|------|
| 0x00 | bBootLunEn | 부팅 LUN 선택 |
| 0x02 | bCurrentPowerMode | 현재 전력 모드 |
| 0x04 | bActiveICCLevel | 활성 전류 소비 수준 |
| 0x0F | bRefClkFreq | 기준 클록 주파수 |
| 0x11 | dDynCapNeeded | 동적 용량 요구 |
| 0x14 | wContextConf | 문맥 설정 |
| 0x1B | bWriteBoosterBufferRestoringInd | WB 버퍼 복원 중 여부 |

---

## 8. UFS 명령어 집합 (UCS)

### 8.1 개요

UFS 명령어 집합(UCS)은 **SCSI 아키텍처 모델**을 기반으로 한다. 표준 SCSI 명령의 부분 집합에 UFS 전용 확장 명령이 추가된다.

### 8.2 지원 SCSI 명령어

| 명령어 | OpCode | 설명 |
|--------|--------|------|
| TEST UNIT READY | 0x00 | 장치 준비 상태 확인 |
| REQUEST SENSE | 0x03 | 에러 정보 조회 |
| FORMAT UNIT | 0x04 | 장치 포맷 |
| READ (6) | 0x08 | 6바이트 CDB 읽기 |
| WRITE (6) | 0x0A | 6바이트 CDB 쓰기 |
| INQUIRY | 0x12 | 장치 식별 정보 조회 |
| START STOP UNIT | 0x1B | 장치 전원 상태 제어 |
| READ CAPACITY (10) | 0x25 | 용량 정보 조회 (10바이트) |
| READ (10) | 0x28 | 10바이트 CDB 읽기 |
| WRITE (10) | 0x2A | 10바이트 CDB 쓰기 |
| SYNCHRONIZE CACHE (10) | 0x35 | 캐시 동기화 |
| WRITE BUFFER | 0x3B | 펌웨어 다운로드 |
| READ BUFFER | 0x3C | 버퍼 읽기 |
| UNMAP | 0x42 | 논리 블록 매핑 해제 (TRIM) |
| READ (16) | 0x88 | 16바이트 CDB 읽기 |
| WRITE (16) | 0x8A | 16바이트 CDB 쓰기 |
| PRE-FETCH (16) | 0x90 | 데이터 사전 읽기 |
| SYNCHRONIZE CACHE (16) | 0x91 | 캐시 동기화 (16바이트) |
| REPORT LUNS | 0xA0 | LUN 목록 조회 |
| READ CAPACITY (16) | 0x9E | 용량 정보 조회 (16바이트) |

### 8.3 Security Protocol 명령어 (RPMB)

| 명령어 | OpCode | 설명 |
|--------|--------|------|
| SECURITY PROTOCOL IN | 0xA2 | RPMB 데이터 읽기 |
| SECURITY PROTOCOL OUT | 0xB5 | RPMB 데이터 쓰기 |

### 8.4 HPB 관련 명령어

| 명령어 | OpCode | 설명 |
|--------|--------|------|
| READ BUFFER (16) | 0x9B | HPB 맵 데이터 읽기 |
| HPB READ (16) | 0xE8 | HPB 힌트 포함 읽기 |

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

| 상태 | 설명 | 복귀 시간 |
|------|------|----------|
| Active (HS) | 고속 데이터 전송 | N/A |
| Sleep | UIC 링크 유지, 핵심 회로 저전력 | ~1 ms |
| Hibernate (HIBERN8) | M-PHY 링크 비활성화, 최저 전력 | ~1 ms |
| Power Down | 완전 전원 차단 | 장치 초기화 필요 |

### 9.2 전력 소비 클래스

UFS 5.0은 장치의 최대 전류 소비를 등급별로 정의한다.

| ICC Level | 최대 전류 (mA) |
|-----------|--------------|
| Level 0 | 0 |
| Level 1 | 100 |
| Level 2 | 200 |
| Level 3 | 300 |
| Level 4 | 450 |
| Level 5 | 600 |
| Level 6 | 900 |
| Level 7 | 1200 |
| Level 8 | 1500 |
| Level 9 | 2000 |
| Level 10 | 2500 |
| Level 11 | 3000 |
| Level 12 | 3500 |
| Level 13 | 4000 |
| Level 14 | 4500 |
| Level 15 | 5000 |

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

| 항목 | 설명 |
|------|------|
| 최대 파티션 수 | 4개 (UFS 5.0) |
| 파티션 크기 | 128 KB 단위 |
| 접근 방법 | SECURITY PROTOCOL IN/OUT 명령 사용 |

### 10.2 인라인 암호화 (Inline Encryption)

UFS 5.0은 장치 내부에서 데이터 암호화/복호화를 수행하는 인라인 암호화를 지원한다.

- **알고리즘**: AES-256-XTS (필수), AES-128-XTS (선택)
- **암호화 단위**: 논리 블록 단위 (512 B 또는 4096 B)
- **키 슬롯**: 호스트가 키 슬롯에 암호화 키 설정 후 I/O 명령과 함께 슬롯 번호 지정

### 10.3 쓰기 방지 (Write Protection)

| 유형 | 설명 |
|------|------|
| 영구 쓰기 방지 | 비가역적, 제조 후 설정 가능 |
| 전원 인가 쓰기 방지 | 전원 차단 후 자동 해제 |
| 일시적 쓰기 방지 | 소프트웨어로 설정/해제 가능 |

---

## 11. 성능 특성

### 11.1 세대별 성능 비교

| 항목 | UFS 3.1 | UFS 4.0 | UFS 5.0 |
|------|---------|---------|---------|
| 최대 순차 읽기 | ~2,100 MB/s | ~4,200 MB/s | ~11,600 MB/s |
| 최대 순차 쓰기 | ~1,200 MB/s | ~2,800 MB/s | ~6,000 MB/s |
| 최대 랜덤 읽기 (4K IOPS) | ~100K IOPS | ~200K IOPS | ~400K IOPS |
| 최대 랜덤 쓰기 (4K IOPS) | ~70K IOPS | ~150K IOPS | ~300K IOPS |
| 최고 기어 | HS-G4 (NRZ) | HS-G5 (NRZ) | **HS-G6 (PAM4)** |
| 레인당 최대 속도 | 9.984 Gbps | 23.2 Gbps | **46.4 Gbps** |
| x2 링크 최대 속도 | ~19.9 Gbps | ~46.4 Gbps | **~92.8 Gbps** |
| 최대 큐 깊이 | 32 | 32 | 256 |

> 실제 성능은 장치 제조사, 낸드 플래시 유형(TLC/QLC), 동작 온도 등에 따라 상이하다.

### 11.2 Write Booster (WB)

Write Booster는 SLC 캐시 영역을 활용하여 쓰기 성능을 일시적으로 향상시키는 기능이다.

| 항목 | 설명 |
|------|------|
| 버퍼 크기 | 제조사 정의 (최대 수 GB) |
| 버퍼 유형 | 공유 버퍼 또는 LUN별 전용 버퍼 |
| 플러시 정책 | 자동 또는 호스트 제어 |
| 활성화 방법 | `fWriteBoosterEn` 플래그 설정 |

#### WB 버퍼 수명 지시자

| bAvailableWBBufferSize 값 | 의미 |
|--------------------------|------|
| 0x00 | 버퍼 소진 (0%) |
| 0x01–0x0A | 가용 용량 10%–100% |

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

| 필드 | 오프셋 | 크기 | 설명 |
|------|--------|------|------|
| bLength | 0x00 | 1 | 디스크립터 길이 |
| bDescriptorIDN | 0x01 | 1 | 0x00 (Device) |
| bDevice | 0x02 | 1 | 장치 클래스 (0x00: UFS) |
| bDeviceClass | 0x03 | 1 | 서브클래스 |
| bProtocol | 0x04 | 1 | 프로토콜 버전 |
| bNumberLU | 0x05 | 1 | 활성화된 LUN 수 |
| bNumberWLU | 0x06 | 1 | Well-known LUN 수 |
| bBootEnable | 0x07 | 1 | 부팅 LUN 활성화 여부 |
| bDescrAccessEn | 0x08 | 1 | 디스크립터 접근 허용 |
| bInitPowerMode | 0x09 | 1 | 초기 전력 모드 |
| bHighPriorityLUN | 0x0A | 1 | 고우선순위 LUN |
| bSecureRemovalType | 0x0B | 1 | 보안 삭제 유형 |
| bSecurityLU | 0x0C | 1 | 보안 LUN 지원 여부 |
| bBackgroundOpsTermLat | 0x0D | 1 | 백그라운드 작업 종료 지연 |
| bInitActiveICCLevel | 0x0E | 1 | 초기 전류 소비 등급 |
| wSpecVersion | 0x10 | 2 | 규격 버전 |
| wManufactureDate | 0x12 | 2 | 제조 날짜 |
| iManufacturerName | 0x14 | 1 | 제조사명 인덱스 |
| iProductName | 0x15 | 1 | 제품명 인덱스 |
| iSerialNumber | 0x16 | 1 | 시리얼 번호 인덱스 |
| iOemID | 0x17 | 1 | OEM ID 인덱스 |
| wManufacturerID | 0x18 | 2 | 제조사 ID (JEDEC) |
| bUD0BaseOffset | 0x1A | 1 | Unit Descriptor 0 오프셋 |
| bUDConfigPLength | 0x1B | 1 | Unit Descriptor 설정 길이 |
| bDeviceRTTCap | 0x1C | 1 | 최대 동시 RTT 수 |
| wPeriodicRTCUpdate | 0x1D | 2 | 주기적 RTC 갱신 |
| bUFSFeaturesSupport | 0x1F | 1 | 지원 기능 비트맵 |
| bFFUTimeout | 0x20 | 1 | FFU 타임아웃 |
| bQueueDepth | 0x21 | 1 | 최대 큐 깊이 |
| wDeviceVersion | 0x24 | 2 | 장치 버전 |
| bNumSecureWPArea | 0x26 | 1 | 보안 쓰기 방지 영역 수 |
| dPSAMaxDataSize | 0x27 | 4 | PSA 최대 데이터 크기 |
| bPSAStateTimeout | 0x2B | 1 | PSA 상태 타임아웃 |
| iProductRevisionLevel | 0x2C | 1 | 제품 리비전 인덱스 |

### 12.2 지오메트리 디스크립터 (Geometry Descriptor)

| 필드 | 오프셋 | 크기 | 설명 |
|------|--------|------|------|
| bLength | 0x00 | 1 | 디스크립터 길이 |
| bDescriptorIDN | 0x01 | 1 | 0x05 (Geometry) |
| bMediaTechnology | 0x02 | 1 | 미디어 기술 유형 |
| qTotalRawDeviceCapacity | 0x04 | 8 | 전체 원시 용량 (512 B 섹터) |
| bMaxNumberLU | 0x0C | 1 | 최대 LUN 수 |
| dSegmentSize | 0x0D | 4 | 세그먼트 크기 (512 B 단위) |
| bAllocationUnitSize | 0x11 | 1 | 할당 단위 크기 (세그먼트 수) |
| bMinAddrBlockSize | 0x12 | 1 | 최소 주소 지정 블록 크기 |
| bOptimalReadBlockSize | 0x13 | 1 | 최적 읽기 블록 크기 |
| bOptimalWriteBlockSize | 0x14 | 1 | 최적 쓰기 블록 크기 |
| bMaxInBufferSize | 0x15 | 1 | 최대 입력 버퍼 크기 |
| bMaxOutBufferSize | 0x16 | 1 | 최대 출력 버퍼 크기 |
| bRPMB_ReadWriteSize | 0x17 | 1 | RPMB 읽기/쓰기 크기 |
| bDynamicCapacityResourcePolicy | 0x18 | 1 | 동적 용량 정책 |
| bDataOrdering | 0x19 | 1 | 데이터 순서 지원 |
| bMaxContexIDNumber | 0x1A | 1 | 최대 컨텍스트 ID 수 |
| bSysDataTagUnitSize | 0x1B | 1 | 시스템 데이터 태그 단위 |
| bSysDataTagResSize | 0x1C | 1 | 시스템 데이터 태그 예약 크기 |
| bSupportedSecRTypes | 0x1D | 1 | 지원 보안 삭제 유형 |
| wSupportedMemoryTypes | 0x1E | 2 | 지원 메모리 유형 비트맵 |
| dSystemCodeMaxNAllocU | 0x20 | 4 | 시스템 코드 최대 할당 단위 |
| wSystemCodeCapAdjFac | 0x24 | 2 | 시스템 코드 용량 조정 계수 |
| dNonPersistMaxNAllocU | 0x26 | 4 | 비영구 최대 할당 단위 |
| wNonPersistCapAdjFac | 0x2A | 2 | 비영구 용량 조정 계수 |

### 12.3 장치 건강 디스크립터 (Device Health Descriptor)

장치의 수명 정보를 제공한다.

| 필드 | 오프셋 | 크기 | 설명 |
|------|--------|------|------|
| bLength | 0x00 | 1 | 디스크립터 길이 |
| bDescriptorIDN | 0x01 | 1 | 0x07 |
| bPreEOLInfo | 0x02 | 1 | 사전 EOL 상태 (01h: 정상, 02h: 경고, 03h: 긴급) |
| bDeviceLifeTimeEstA | 0x03 | 1 | 수명 추정 A (0%–90%+ 범위) |
| bDeviceLifeTimeEstB | 0x04 | 1 | 수명 추정 B |
| VendorPropInfo | 0x05 | 32 | 제조사 정의 정보 |

---

## 13. 오류 처리

### 13.1 UPIU 응답 코드 (Response Code)

| 코드 | 의미 |
|------|------|
| 0x00 | Target Success |
| 0x01 | Target Failure |

### 13.2 Overall Command Status (OCS)

| OCS 값 | 의미 |
|--------|------|
| 0x00 | SUCCESS |
| 0x01 | INVALID_COMMAND_TABLE_ATTRIBUTES |
| 0x02 | INVALID_PRDT_ATTRIBUTES |
| 0x03 | MISMATCH_DATA_BUFFER_SIZE |
| 0x04 | MISMATCH_RESPONSE_UPIU_SIZE |
| 0x05 | PEER_COMMUNICATION_FAILURE |
| 0x06 | ABORTED |
| 0x07 | FATAL_ERROR |

### 13.3 SCSI 체크 조건 (Sense Data)

SCSI 명령 실패 시 장치는 Sense Data를 반환한다.

| Sense Key | 의미 |
|-----------|------|
| 0x01 | RECOVERED ERROR |
| 0x02 | NOT READY |
| 0x03 | MEDIUM ERROR (낸드 읽기 오류) |
| 0x04 | HARDWARE ERROR |
| 0x05 | ILLEGAL REQUEST (잘못된 명령/파라미터) |
| 0x06 | UNIT ATTENTION |
| 0x07 | DATA PROTECT (쓰기 방지 위반) |
| 0x0B | ABORTED COMMAND |

### 13.4 오류 복구 절차

1. **소프트 오류**: 장치 자체 ECC로 복구 (호스트에 투명하게 처리)
2. **정정 불가 오류**: MEDIUM ERROR Sense Key 반환
3. **링크 오류**: UniPro ARQ 재전송 또는 링크 재초기화
4. **작업 중단**: ABORT TASK 작업 관리 명령으로 명령 취소

---

## 14. UFS 5.0 주요 변경사항

UFS 4.0 대비 UFS 5.0에서 신규 도입·변경된 주요 사항은 다음과 같다.

### 14.1 성능 향상

| 항목 | 변경 내용 |
|------|----------|
| M-PHY 기어 | **HS-G6 + PAM4** 신규 추가 (레인당 23.2 Gbps NRZ → 46.4 Gbps PAM4) |
| 신호 방식 | NRZ(2레벨) → **PAM4(4레벨)** 전환, 심볼당 2비트 전송 |
| FEC 도입 | PAM4 SNR 감소 보완을 위한 Forward Error Correction 필수화 |
| 큐 깊이 | 32 → 256으로 확장 |
| 링크 최대 대역폭 | ~46.4 Gbps(UFS 4.0) → **~92.8 Gbps**(UFS 5.0, x2 레인) |
| 순차 읽기 속도 | 최대 ~4,200 MB/s → ~11,600 MB/s |

### 14.2 전력 효율

| 항목 | 변경 내용 |
|------|----------|
| 정밀 전력 제어 | ICC 레벨 세분화, 동적 전압-주파수 조정 지원 |
| Auto-Hibernate | 타이머 해상도 개선 |

### 14.3 보안 강화

| 항목 | 변경 내용 |
|------|----------|
| 인라인 암호화 | AES-256-XTS 필수화 (이전 버전 선택적) |
| RPMB 파티션 수 | 최대 4개 (UFS 4.0: 최대 4개 유지, 접근 방법 개선) |
| 보안 삭제 | 암호 지우기(Crypto Erase) 방식 추가 |

### 14.4 안정성 및 신뢰성

| 항목 | 변경 내용 |
|------|----------|
| 차량용(Automotive) 프로파일 | AEC-Q100 Grade 요구사항 지원, 확장 온도 범위 |
| ECC 강화 | 고급 오류 정정 코드(LDPC) 지원 명시 |
| Refresh 기능 | 낸드 데이터 리텐션 관리를 위한 자동 새로고침 지원 |

### 14.5 기능 확장

| 항목 | 변경 내용 |
|------|----------|
| Context ID | 최대 수 확장, 다중 워크로드 힌트 기능 강화 |
| Write Booster | 다중 LUN 공유 버퍼 정책 개선 |
| HPB 2.0 | 호스트 L2P 맵 캐시 일관성 관리 개선 |
| Zoned Storage | 구역 기반 스토리지 지원(초안 포함) |
| 펌웨어 업데이트 (FFU) | 이중화(A/B) 업데이트 지원 강화 |

### 14.6 규격 번호 요약

| 규격 | 내용 |
|------|------|
| JESD220F | UFS 5.0 메인 규격 |
| JESD220-4 | UFS 5.0 Host Controller Interface (HCI) |
| JESD223F | UFS 5.0 Flash Memory Interface |
| MIPI M-PHY 5.0 | 물리 계층 규격 |
| MIPI UniPro 2.0 | 데이터 링크 계층 규격 |

---

## 15. UFS 4.1 vs UFS 5.0 상세 비교

### 15.1 UFS 4.1 개요

UFS 4.1은 UFS 4.0(JESD220E)의 마이너 리비전으로, 물리 계층 속도는 HS-G5(NRZ, 23.2 Gbps/lane)를 유지하면서 기능 안정성, 전력 관리, 호스트 성능 향상 기능 등을 개선한 버전이다. UFS 5.0은 이 UFS 4.1을 기반으로 물리 계층부터 응용 계층까지 전면적인 성능·기능 업그레이드를 적용한 메이저 리비전이다.

---

### 15.2 물리 계층 (M-PHY) 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| 최고 기어 | HS-G5 | **HS-G6** | 신규 기어 추가 |
| 신호 방식 | NRZ (2레벨) | **PAM4 (4레벨)** | 방식 전환 |
| 레인당 최대 속도 | 23.2 Gbps | **46.4 Gbps** | 2배 증가 |
| x2 레인 최대 속도 | ~46.4 Gbps | **~92.8 Gbps** | 2배 증가 |
| FEC | 미적용 | **RS-FEC 필수** | 신규 요구사항 |
| DSP 등화기 | 선택적 | **필수** (CTLE+DFE+FFE) | 필수화 |
| Eye 마진 | 상대적으로 여유 | 1/3 수준 (PAM4) → FEC로 보상 | SNR 감소 |
| M-PHY 버전 | Gen 5 | **Gen 6** | 버전 업 |
| 지원 레인 수 | x1, x2 | x1, x2 (동일) | 변경 없음 |

#### PAM4 도입 배경

UFS 4.1까지는 NRZ 방식으로 HS-G5의 23.2 Gbps/lane이 물리적 한계에 근접했다. 동일 채널(패키지 배선, PCB 트레이스, 커넥터)에서 더 높은 속도를 달성하기 위해 **보 레이트(Baud Rate)는 유지하고 신호 레벨을 4단계로 늘리는 PAM4** 방식을 채택했다.

```
UFS 4.1 HS-G5 (NRZ):     23.2 Gbaud × 1 bit/symbol = 23.2 Gbps
UFS 5.0 HS-G6 (PAM4):    23.2 Gbaud × 2 bit/symbol = 46.4 Gbps
                          └─ 같은 채널, 같은 클록, 2배 데이터
```

---

### 15.3 성능 비교

| 항목 | UFS 4.1 | UFS 5.0 | 향상률 |
|------|---------|---------|--------|
| 최대 순차 읽기 | ~4,200 MB/s | ~11,600 MB/s | **+176%** |
| 최대 순차 쓰기 | ~2,800 MB/s | ~6,000 MB/s | **+114%** |
| 최대 랜덤 읽기 (4K) | ~200K IOPS | ~400K IOPS | **+100%** |
| 최대 랜덤 쓰기 (4K) | ~150K IOPS | ~300K IOPS | **+100%** |
| 최대 큐 깊이 | 32 | **256** | **8배** |
| 읽기 지연(Latency) | ~60 µs (typ) | ~50 µs (typ) | 소폭 개선 |
| 링크 최대 대역폭 | ~46.4 Gbps | **~92.8 Gbps** | **2배** |

#### 큐 깊이 256의 의미

UFS 4.1의 큐 깊이 32는 모바일 워크로드에서는 충분했으나, 서버·자동차·PC SSD 용도에서는 병렬 I/O 처리 능력이 제한되었다. UFS 5.0의 **큐 깊이 256**은 NVMe SSD 수준에 근접하여 고부하 랜덤 I/O 환경에서 처리량과 공정성(Fairness)이 크게 향상된다.

```
큐 깊이별 4K 랜덤 읽기 성능 (개념도):

IOPS
 ▲
 │                                    ●── UFS 5.0 (QD256)
 │                          ●
 │               ●
 │     ●──────────────────────────── UFS 4.1 (QD32 포화)
 └─────┴────┴────┴────┴────┴──────→  Queue Depth
       1    4   16   32  64  256
```

---

### 15.4 전력 관리 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| 전력 모드 | Active / Sleep / HIBERN8 / Power Down | 동일 + 개선 | 모드 체계 유지 |
| Deep Sleep | 지원 | 지원 (개선) | 복귀 시간 단축 |
| Auto-Hibernate | 지원 | 지원 (개선) | 타이머 해상도 향상 |
| 성능 당 전력 (W/GBps) | 기준 | **대폭 개선** | PAM4로 전력 효율 향상 |
| 활성 전류 (HS 전송 중) | ~900 mA (typ) | ~900 mA (typ, 고속) | 유사, 단 처리량 2배 |
| HIBERN8 진입/복귀 | ~1 ms | ~1 ms (유사) | 변경 없음 |
| PAM4 PHY 전력 | N/A | DSP/FEC 추가 소비 | 회로 복잡도 증가 |

> **핵심**: UFS 5.0은 절대 소비 전력이 소폭 증가하지만 처리량이 2배이므로 **단위 전송량 당 전력(pJ/bit)** 효율은 개선된다.

#### ICC 레벨 변화

UFS 4.1과 UFS 5.0 모두 동일한 ICC 레벨 체계(Level 0~15)를 사용하나, UFS 5.0 HS-G6 동작 시 상위 ICC 레벨(Level 12~15)이 실제 동작 범위로 사용되는 빈도가 증가한다.

---

### 15.5 보안 기능 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| 인라인 암호화 | AES-128/256-XTS (선택) | **AES-256-XTS 필수** | 필수화 |
| 암호화 키 슬롯 수 | 최대 32 | **최대 64** | 확장 |
| RPMB 파티션 수 | 최대 4 | 최대 4 (동일) | 변경 없음 |
| RPMB 인증 알고리즘 | HMAC-SHA256 | HMAC-SHA256 / **HMAC-SHA512** | 알고리즘 추가 |
| 보안 삭제 유형 | Overwrite / Block Erase | + **Crypto Erase** 강화 | 방식 추가 |
| Replay Protection | RPMB 카운터 기반 | 동일 + 카운터 오버플로 처리 개선 | 안정성 향상 |
| Secure Boot 지원 | 부트 파티션 쓰기 방지 | 동일 + 무결성 검증 강화 | 강화 |

#### 인라인 암호화 필수화의 의미

UFS 4.1까지는 구현이 선택 사항이었으나, UFS 5.0부터는 **모든 인증 장치가 AES-256-XTS 인라인 암호화를 지원해야 한다.** 이는 분실·도난 기기에서의 데이터 보호를 하드웨어 수준에서 보장하기 위함이다.

```
암호화 흐름 (UFS 5.0):
호스트 OS
  │ 암호화 키 + 슬롯 번호 설정 (초기화 시)
  ↓
UFS HCI (CRYPTO_LBA_UNIT 등 설정)
  │ I/O 명령에 슬롯 번호 태그
  ↓
UFS 장치 PHY 직전 인라인 AES-256-XTS 엔진
  │ 논리 블록 주소(LBA)를 Tweak으로 사용
  ↓
낸드 플래시 (암호화된 데이터 저장)
```

---

### 15.6 Write Booster (WB) 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| WB 기본 동작 | SLC 캐시 활용 | 동일 | 유지 |
| 버퍼 구성 방식 | 공유 버퍼 / LUN별 전용 버퍼 | 동일 + **멀티 스트림 연동** | 스트림별 WB 힌트 |
| 버퍼 플러시 제어 | 호스트 또는 자동 | 동일 + **우선순위 기반 플러시** | 세분화 |
| WB 버퍼 수명 지시자 | bAvailableWBBufferSize (0~10) | 동일 + **더 세분화된 지시자** | 정밀도 향상 |
| 최대 WB 버퍼 크기 | 수 GB (제조사 정의) | 동일 (확장 가능) | 상한 완화 |
| WB 상태 보고 | 기본 | **Exception Event 연동** | 실시간 통보 |

---

### 15.7 HPB (Host Performance Booster) 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| HPB 버전 | HPB 1.0 / 2.0 | **HPB 2.0 이상** | 기능 완성 |
| L2P 맵 크기 제한 | 장치 정의 | 확장 가능 | 상한 완화 |
| Sub-region 크기 | 고정 | **동적 설정 가능** | 유연성 향상 |
| 캐시 무효화 처리 | Active region invalidation | **세분화된 Dirty region 관리** | 일관성 개선 |
| HPB READ 명령 | READ(16) 확장 | 동일 | 유지 |
| 호스트 DRAM 사용 | 선택적 | 동일 (선택적) | 유지 |
| 랜덤 읽기 개선 효과 | 최대 ~40% 향상 | 최대 ~40% 향상 (기반 성능 2배) | 기반 성능 증가로 절대치 향상 |

#### HPB 동작 개선 상세

UFS 4.1의 HPB 2.0 대비 UFS 5.0에서 개선된 핵심은 **L2P 맵 캐시의 유효성(Validity) 관리 정밀도**이다. 빠른 쓰기(WB 활용)로 인해 물리 주소가 자주 변경되는 환경에서 호스트 캐시와 장치 실제 L2P 맵 간의 불일치(Staleness)가 발생하기 쉬운데, UFS 5.0은 Dirty region 보고 단위를 세분화하여 불필요한 캐시 무효화를 줄였다.

---

### 15.8 신뢰성 및 차량용(Automotive) 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| 동작 온도 범위 | -25°C ~ +85°C (표준) | **-40°C ~ +105°C** | 차량용 확장 |
| AEC-Q100 Grade | Grade 2 (일부) | **Grade 1 필수** | 요구 수준 강화 |
| ISO 26262 | 부분 지원 (ASIL-B 수준) | **ASIL-B/D** 지원 강화 | 기능 안전 강화 |
| Refresh 동작 | 백그라운드 자동 | 동일 + **호스트 트리거 Refresh** | 제어권 추가 |
| 사전 EOL 경고 | bPreEOLInfo (3단계) | 동일 + **세부 경고 세분화** | 예측 정밀도 향상 |
| DRAM-less 동작 | 선택적 지원 | **완전 지원** | 차량용 BOM 최적화 |
| 데이터 보존성 | JESD47 기준 | **강화된 리텐션 요구** | 장기 보존 보장 |
| Background Ops 제어 | 기본 | **호스트 개입 시점 명확화** | 예측 가능성 향상 |
| Exception Event | 기본 지원 | **세분화 및 응답 속도 개선** | 실시간 모니터링 강화 |

---

### 15.9 프로토콜 및 명령어 비교

| 항목 | UFS 4.1 | UFS 5.0 | 변화 |
|------|---------|---------|------|
| UPIU 기본 구조 | 동일 | 동일 | 하위 호환 유지 |
| 최대 큐 깊이 (Task Tag) | 32 (5비트) | **256 (8비트)** | Task Tag 필드 확장 |
| UniPro 버전 | 1.x | **2.0** | 버전 업 |
| NOP UPIU 타임아웃 | 고정 | **동적 조정** | 유연성 향상 |
| Zoned Storage 지원 | 미지원 | **부분 지원 (선택적)** | 신규 |
| Context ID 수 | 최대 8 | **최대 16** | 확장 |
| 멀티 스트림 | 기본 | **스트림별 QoS 힌트** 강화 | 세분화 |
| 초기화 시간 | ~수십 ms | 동일 수준 | 변화 없음 |

#### Zoned Storage 도입 배경

UFS 5.0에서 선택적으로 도입된 Zoned Storage는 낸드 플래시 특성(순차 쓰기가 효율적)을 호스트 레벨에서 명시적으로 활용하는 방식이다. 특정 Zone에 대해서는 반드시 순차 쓰기를 강제하여 장치 내부 GC(Garbage Collection) 부담을 줄이고, 쓰기 증폭(Write Amplification)을 최소화한다.

```
일반 LUN (UFS 4.1/5.0):         Zoned LUN (UFS 5.0 선택):
┌─────────────────────┐          ┌──────────────────────────┐
│ 임의 주소 쓰기 가능   │          │ Zone 0: 순차 쓰기만 가능  │
│ FTL이 내부 관리      │          │ Zone 1: 순차 쓰기만 가능  │
│ GC 오버헤드 발생     │          │ Zone 2: 비어 있음(초기화) │
└─────────────────────┘          │ → GC 최소화, WAF 감소    │
                                  └──────────────────────────┘
```

---

### 15.10 하위 호환성

| 항목 | 내용 |
|------|------|
| UFS 5.0 장치 + UFS 4.1 호스트 | HS-G5(NRZ) 기어로 폴백하여 동작, PAM4/HS-G6 비활성화 |
| UFS 4.1 장치 + UFS 5.0 호스트 | HS-G5(NRZ) 기어로 동작, 최대 성능은 UFS 4.1 수준 |
| UPIU 호환성 | 완전 하위 호환 (동일 UPIU 구조 유지) |
| 디스크립터 호환성 | 기존 디스크립터 유지, UFS 5.0 신규 필드는 미지원 장치에서 0x00 반환 |
| 물리 인터페이스 | 동일 핀 배열, 동일 커넥터 (PAM4는 신호 처리 방식만 변경) |

> UFS 5.0의 PAM4 모드 사용 여부는 링크 초기화 과정의 기어/모드 협상 단계에서 결정되며, 어느 한쪽이 HS-G6를 지원하지 않으면 자동으로 HS-G5 이하로 폴백한다.

---

### 15.11 전체 비교 요약표

| 분류 | 항목 | UFS 4.1 | UFS 5.0 |
|------|------|---------|---------|
| **물리** | 최고 기어 | HS-G5 (NRZ) | **HS-G6 (PAM4)** |
| **물리** | 레인당 속도 | 23.2 Gbps | **46.4 Gbps** |
| **물리** | x2 링크 속도 | ~46.4 Gbps | **~92.8 Gbps** |
| **물리** | FEC | 미적용 | **RS-FEC 필수** |
| **물리** | DSP 등화기 | 선택 | **필수** |
| **성능** | 순차 읽기 | ~4,200 MB/s | **~11,600 MB/s** |
| **성능** | 순차 쓰기 | ~2,800 MB/s | **~6,000 MB/s** |
| **성능** | 랜덤 읽기 (4K) | ~200K IOPS | **~400K IOPS** |
| **성능** | 큐 깊이 | 32 | **256** |
| **보안** | 인라인 암호화 | 선택적 | **AES-256-XTS 필수** |
| **보안** | RPMB 인증 | HMAC-SHA256 | **+ HMAC-SHA512** |
| **보안** | 암호화 키 슬롯 | 최대 32 | **최대 64** |
| **기능** | Zoned Storage | 미지원 | **선택적 지원** |
| **기능** | Context ID | 최대 8 | **최대 16** |
| **기능** | HPB | 2.0 | **2.0 이상 (개선)** |
| **전력** | Deep Sleep | 지원 | 지원 (복귀 시간 단축) |
| **전력** | 단위 전력 효율 | 기준 | **향상 (처리량 2배)** |
| **차량** | 동작 온도 | ~+85°C | **~+105°C** |
| **차량** | AEC-Q100 | Grade 2 | **Grade 1** |
| **차량** | ISO 26262 | 부분 | **ASIL-B/D 강화** |
| **호환** | 하위 호환 | — | **UFS 4.1과 완전 호환** |

---

## 참고 문헌

1. JEDEC Standard JESD220F — *Universal Flash Storage (UFS) Version 5.0*, JEDEC Solid State Technology Association
2. JEDEC Standard JESD220-4 — *UFS Host Controller Interface (UFSHCI)*
3. MIPI Alliance Specification for M-PHY, Version 5.0
4. MIPI Alliance Specification for UniPro, Version 2.0
5. JEDEC Standard JESD223 — *UFS Flash Memory Interface*
6. JEDEC White Paper: *Introduction to Universal Flash Storage (UFS)*

---

*본 문서는 UFS 5.0 공개 기술 자료를 바탕으로 작성된 한국어 번역 요약본입니다. 법적 효력이 있는 원문 규격은 JEDEC 공식 웹사이트(www.jedec.org)에서 구입하시기 바랍니다.*
