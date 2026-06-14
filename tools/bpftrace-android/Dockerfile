# Android(aarch64)용 bpftrace 정적(static) 바이너리 크로스빌드
# =============================================================
# Android 는 bionic libc 라서, glibc 로 동적링크된 리눅스 bpftrace 는 폰에서
# 실행되지 않는다. musl 기반 Alpine 에서 "정적 링크"로 빌드하면 libc 의존이
# 사라져 Android 에서도 그대로 실행된다.
#
# x86_64 PC 에서 arm64 를 빌드하려면 QEMU binfmt 가 필요하다(build.sh 참고):
#   docker run --privileged --rm tonistiigi/binfmt --install arm64
#
# 사용:
#   ./build.sh                 # out/bpftrace 생성
#   file out/bpftrace          # "ELF 64-bit ... ARM aarch64 ... statically linked"
#
# 주의: 패키지명/플래그는 Alpine·bpftrace 버전에 따라 달라질 수 있다. 빌드가
#       막히면 BPFTRACE_VERSION / ALPINE_VERSION 을 조정하거나, 아래 apk 목록을
#       해당 버전 문서에 맞게 손보면 된다(베스트-에포트 레시피).

# syntax=docker/dockerfile:1
ARG ALPINE_VERSION=3.20
FROM --platform=linux/arm64 alpine:${ALPINE_VERSION} AS build

# bpftrace 빌드 의존성(정적 라이브러리 포함). LLVM/Clang 이 가장 무겁다.
RUN apk add --no-cache \
        build-base cmake git ninja \
        flex flex-dev bison \
        llvm-dev llvm-static clang-dev clang-static \
        libbpf-dev \
        elfutils-dev libelf-static \
        zlib-dev zlib-static \
        binutils-dev \
        cereal \
        linux-headers \
        bcc-dev || true
# 일부 Alpine 버전은 패키지명이 다를 수 있어 || true 로 1차 시도 후,
# 빌드 단계에서 부족분이 드러나면 README 의 안내대로 보완한다.

ARG BPFTRACE_VERSION=v0.20.4
RUN git clone --depth 1 --branch ${BPFTRACE_VERSION} \
        https://github.com/bpftrace/bpftrace.git /src

WORKDIR /src
RUN cmake -G Ninja -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DSTATIC_LINKING=ON \
        -DBUILD_TESTING=OFF \
    && cmake --build build -j "$(nproc)" \
    && (strip build/src/bpftrace || true) \
    && build/src/bpftrace --version

# 결과 바이너리만 호스트로 내보내기 위한 스테이지
FROM scratch AS export
COPY --from=build /src/build/src/bpftrace /bpftrace
