# Android(aarch64)용 bpftrace 정적 바이너리 빌드

`python -m android_ftrace_tool.bpftrace run ...` 으로 eBPF 상관 스크립트를 폰에서
돌리려면, **폰에 맞는 bpftrace 바이너리**가 필요합니다. 여기 도구는 그중 가장
재현성 좋은 **방법 C(정적 크로스컴파일)** 를 자동화합니다.

> 더 쉬운 경로가 있으면 그쪽을 먼저 쓰세요:
> - **방법 A**: AOSP 트리에서 `m bpftrace` (userdebug 빌드 환경이 있으면 최선)
> - **방법 B**: 이미 만들어진 **정적 aarch64** 바이너리를 구해서 push
> - **방법 C**: (이 디렉터리) Docker 로 직접 정적 빌드

## 왜 "정적(static)" 인가?

Android 는 bionic libc 입니다. glibc 로 동적링크된 일반 리눅스 bpftrace 는 폰에서
`CANNOT LINK EXECUTABLE` 로 죽습니다. **musl 기반 Alpine 에서 정적 링크**하면 libc
의존이 사라져 Android 에서도 그대로 실행됩니다.

## 사전 요구

- Docker (`buildx` 포함, 19.03+)
- x86_64 PC 에서 arm64 를 빌드하므로 **QEMU binfmt** (build.sh 가 자동 설치 시도)
- 디스크 ~수 GB, 시간 수십 분(LLVM 빌드가 무거움)

## 사용

```bash
cd tools/bpftrace-android
./build.sh
# 버전 바꾸려면:
BPFTRACE_VERSION=v0.20.4 ALPINE_VERSION=3.20 ./build.sh
```

성공하면 `out/bpftrace` 가 생기고, 마지막에 다음을 확인하세요:

```bash
file out/bpftrace
# 예: ELF 64-bit LSB executable, ARM aarch64, ... statically linked, stripped
```

`statically linked` 가 보여야 합니다(`dynamically linked` 면 Android 에서 안 됨).

## 폰에 올리고 검증

```bash
adb push out/bpftrace /data/local/tmp/
adb shell su -c 'chmod 755 /data/local/tmp/bpftrace'

# 커널 준비도 + 바이너리 동작 한 번에 점검
python -m android_ftrace_tool.bpftrace check \
       --bpftrace /data/local/tmp/bpftrace --su

# 실제 상관 스크립트 실행(예: 블록 I/O 지연 10초)
python -m android_ftrace_tool.bpftrace run block_latency \
       --bpftrace /data/local/tmp/bpftrace --duration 10 --su
```

## 빌드가 막힐 때 (베스트-에포트 레시피라 환경별 보정 필요)

bpftrace/Alpine 버전에 따라 패키지명·CMake 옵션이 달라질 수 있습니다.

- **패키지 못 찾음**: `Dockerfile` 의 `apk add ...` 목록을 해당 Alpine 버전의
  패키지명으로 수정(예: `llvm-static` ↔ `llvm17-static`).
- **정적 라이브러리 부족**: `-static` 계열 패키지(`zlib-static`, `libelf-static`,
  `llvm-static`, `clang-static`)가 깔렸는지 확인.
- **STATIC_LINKING 미지원 버전**: bpftrace 버전을 올리거나(`BPFTRACE_VERSION`),
  CMake 옵션을 해당 버전 문서에 맞게 조정.
- **BTF 필요**: 빌드와 별개로, 실행 폰 커널에 `CONFIG_DEBUG_INFO_BTF=y` 와
  `/sys/kernel/btf/vmlinux` 가 있어야 kprobe 스크립트가 잘 됩니다(`check` 로 확인).

이 방법이 번거로우면, bpftrace 없이 동작하는 **ftrace 기반 기능**(`g`/`h` +
`analyzer.py`)으로도 상관·지연 분석이 가능합니다(메인 매뉴얼 참고).
