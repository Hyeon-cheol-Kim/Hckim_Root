#!/usr/bin/env bash
# Android(aarch64)용 bpftrace 정적 바이너리 빌드 래퍼.
#   결과: ./out/bpftrace  (정적 링크 aarch64 ELF)
#
# 환경변수로 버전 조정 가능:
#   BPFTRACE_VERSION=v0.20.4 ALPINE_VERSION=3.20 ./build.sh
set -euo pipefail

cd "$(dirname "$0")"

BPFTRACE_VERSION="${BPFTRACE_VERSION:-v0.20.4}"
ALPINE_VERSION="${ALPINE_VERSION:-3.20}"
OUT_DIR="${OUT_DIR:-out}"

echo "==> bpftrace ${BPFTRACE_VERSION} (alpine ${ALPINE_VERSION}) for arm64"

# 1) buildx 사용 가능 여부 확인
if ! docker buildx version >/dev/null 2>&1; then
    echo "[오류] 'docker buildx' 가 필요합니다(Docker 19.03+)." >&2
    exit 1
fi

# 2) arm64 에뮬레이션(binfmt) 준비 — x86_64 호스트에서 arm64 빌드 시 필요
if ! docker run --rm --platform linux/arm64 alpine:"${ALPINE_VERSION}" true 2>/dev/null; then
    echo "==> arm64 에뮬레이션 설치(binfmt)"
    docker run --privileged --rm tonistiigi/binfmt --install arm64
fi

# 3) 빌드 후 결과 바이너리를 OUT_DIR 로 내보내기(export 스테이지)
mkdir -p "${OUT_DIR}"
docker buildx build \
    --platform linux/arm64 \
    --build-arg "BPFTRACE_VERSION=${BPFTRACE_VERSION}" \
    --build-arg "ALPINE_VERSION=${ALPINE_VERSION}" \
    --target export \
    --output "type=local,dest=${OUT_DIR}" \
    .

echo
echo "==> 완료: ${OUT_DIR}/bpftrace"
file "${OUT_DIR}/bpftrace" || true
echo
echo "다음 단계(폰에 올리고 실행):"
echo "  adb push ${OUT_DIR}/bpftrace /data/local/tmp/"
echo "  adb shell su -c 'chmod 755 /data/local/tmp/bpftrace'"
echo "  python -m android_ftrace_tool.bpftrace check --bpftrace /data/local/tmp/bpftrace --su"
