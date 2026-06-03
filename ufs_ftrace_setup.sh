#!/bin/bash
# UFS ftrace setup script for Android - fio workload profiling

set -e

TRACE_DIR="/sys/kernel/debug/tracing"
OUTPUT_DIR="${1:-/data/local/tmp}"
TRACE_FILE="${OUTPUT_DIR}/ufs_trace.txt"
BUFFER_SIZE_KB="${2:-65536}"

# ── helpers ──────────────────────────────────────────────────────────────────

die() { echo "[ERROR] $*" >&2; exit 1; }
log() { echo "[$(date '+%H:%M:%S')] $*"; }

require_root() {
    [ "$(id -u)" -eq 0 ] || die "Run as root (adb root first)"
}

mount_debugfs() {
    if ! mountpoint -q /sys/kernel/debug; then
        log "Mounting debugfs..."
        mount -t debugfs debugfs /sys/kernel/debug || die "Failed to mount debugfs"
    fi
}

check_events() {
    local missing=0
    for ev in \
        events/block/block_bio_queue \
        events/block/block_rq_issue \
        events/block/block_rq_complete \
        events/ufs/ufshcd_command
    do
        if [ ! -d "${TRACE_DIR}/${ev}" ]; then
            echo "[WARN] Trace event not found: ${ev}"
            missing=$((missing + 1))
        fi
    done
    [ "$missing" -eq 0 ] && log "All trace events available." || log "${missing} event(s) missing (kernel may not support them)."
}

# ── commands ─────────────────────────────────────────────────────────────────

cmd_setup() {
    require_root
    mount_debugfs
    check_events

    log "Stopping any existing trace..."
    echo 0 > "${TRACE_DIR}/tracing_on"
    echo > "${TRACE_DIR}/trace"                      # clear buffer

    log "Setting buffer size to ${BUFFER_SIZE_KB} KB per CPU..."
    echo "${BUFFER_SIZE_KB}" > "${TRACE_DIR}/buffer_size_kb"

    log "Enabling trace events..."

    # Block layer (process info: comm, pid, rwbs, nr_sector)
    for ev in block_bio_queue block_rq_issue block_rq_complete block_rq_insert block_getrq; do
        path="${TRACE_DIR}/events/block/${ev}/enable"
        [ -f "$path" ] && echo 1 > "$path" && echo "  + block/${ev}"
    done

    # UFS host controller driver
    for ev in ufshcd_command ufshcd_uic_command ufshcd_clk_gating ufshcd_profile_hibern8; do
        path="${TRACE_DIR}/events/ufs/${ev}/enable"
        [ -f "$path" ] && echo 1 > "$path" && echo "  + ufs/${ev}"
    done

    # Print TGID so thread group is visible in output
    echo 1 > "${TRACE_DIR}/options/print-tgid" 2>/dev/null || true

    log "Setup complete. Run '$(basename "$0") start' to begin tracing."
}

cmd_start() {
    require_root
    [ -d "$TRACE_DIR" ] || die "debugfs not mounted - run setup first"
    echo > "${TRACE_DIR}/trace"    # clear buffer before new run
    echo 1 > "${TRACE_DIR}/tracing_on"
    log "Tracing STARTED."
}

cmd_stop() {
    require_root
    echo 0 > "${TRACE_DIR}/tracing_on"
    log "Tracing STOPPED."

    mkdir -p "${OUTPUT_DIR}"
    log "Saving trace to ${TRACE_FILE} ..."
    cat "${TRACE_DIR}/trace" > "${TRACE_FILE}"
    local lines
    lines=$(wc -l < "${TRACE_FILE}")
    log "Saved ${lines} lines -> ${TRACE_FILE}"
}

cmd_status() {
    require_root
    local on
    on=$(cat "${TRACE_DIR}/tracing_on" 2>/dev/null || echo "?")
    local buf
    buf=$(cat "${TRACE_DIR}/buffer_size_kb" 2>/dev/null || echo "?")
    echo "tracing_on    : ${on}"
    echo "buffer_size_kb: ${buf}"
    echo ""
    echo "Enabled events:"
    for ev in \
        events/block/block_bio_queue \
        events/block/block_rq_issue \
        events/block/block_rq_complete \
        events/block/block_rq_insert \
        events/block/block_getrq \
        events/ufs/ufshcd_command \
        events/ufs/ufshcd_uic_command \
        events/ufs/ufshcd_clk_gating \
        events/ufs/ufshcd_profile_hibern8
    do
        path="${TRACE_DIR}/${ev}/enable"
        if [ -f "$path" ]; then
            val=$(cat "$path")
            printf "  %-45s %s\n" "${ev}" "${val}"
        fi
    done
}

cmd_reset() {
    require_root
    log "Disabling all trace events..."
    echo 0 > "${TRACE_DIR}/tracing_on"
    echo 0 > "${TRACE_DIR}/events/block/enable"      2>/dev/null || true
    echo 0 > "${TRACE_DIR}/events/ufs/enable"        2>/dev/null || true
    echo > "${TRACE_DIR}/trace"
    log "Trace reset complete."
}

cmd_run() {
    # Convenience: setup → start → run fio → stop
    # Usage: ufs_ftrace_setup.sh run <fio_args...>
    [ $# -ge 1 ] || die "Usage: $(basename "$0") run <fio command and args>"
    cmd_setup
    cmd_start
    log "Running: fio $*"
    fio "$@"
    cmd_stop
}

# ── usage ─────────────────────────────────────────────────────────────────────

usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [output_dir] [buffer_kb]

Commands:
  setup            Enable trace events (default buffer: 65536 KB)
  start            Clear buffer and start tracing
  stop             Stop tracing and save to <output_dir>/ufs_trace.txt
  status           Show current trace state and enabled events
  reset            Disable all events and clear buffer
  run <fio args>   setup + start + fio + stop in one step

Arguments:
  output_dir       Directory to save trace file (default: /data/local/tmp)
  buffer_kb        Per-CPU trace buffer size in KB (default: 65536)

Examples:
  adb shell $(basename "$0") setup
  adb shell $(basename "$0") start
  adb shell fio /data/local/tmp/seq_write.fio
  adb shell $(basename "$0") stop /sdcard

  # One-shot
  adb shell $(basename "$0") run --filename=/dev/block/sda --rw=write --bs=16k --size=1g --name=test
EOF
}

# ── entry point ───────────────────────────────────────────────────────────────

case "${1:-}" in
    setup)  shift; cmd_setup   "$@" ;;
    start)  shift; cmd_start   "$@" ;;
    stop)   shift; cmd_stop    "$@" ;;
    status) shift; cmd_status  "$@" ;;
    reset)  shift; cmd_reset   "$@" ;;
    run)    shift; cmd_run     "$@" ;;
    *)      usage; exit 1 ;;
esac
