#!/usr/bin/env bash
# PDD Crawler — 后台启动脚本 (WSL / Linux)
# 用法:
#   ./start.sh          启动服务 (默认 0.0.0.0:8000)
#   ./start.sh stop     停止服务
#   ./start.sh restart  重启服务
#   ./start.sh status   查看状态
#   ./start.sh log      查看实时日志

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
PID_FILE="$LOG_DIR/web.pid"
STDOUT_LOG="$LOG_DIR/web_stdout.log"
STDERR_LOG="$LOG_DIR/web_stderr.log"

HOST="${PDD_HOST:-0.0.0.0}"
PORT="${PDD_PORT:-8000}"

# 优先使用 venv 中的 python
if [ -f "$ROOT_DIR/venv/bin/python" ]; then
    PYTHON="$ROOT_DIR/venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

mkdir -p "$LOG_DIR"

_is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

do_start() {
    if _is_running; then
        echo "已在运行 (PID $(cat "$PID_FILE"))"
        return 0
    fi

    echo "启动 PDD Crawler Web ..."
    echo "  Python : $PYTHON"
    echo "  监听   : $HOST:$PORT"
    echo "  日志   : $LOG_DIR"

    nohup "$PYTHON" -m pdd_crawler --host "$HOST" --port "$PORT" \
        >>"$STDOUT_LOG" 2>>"$STDERR_LOG" &

    echo $! > "$PID_FILE"
    sleep 1

    if _is_running; then
        echo "启动成功 (PID $(cat "$PID_FILE"))"
    else
        echo "启动失败，请查看日志: $STDERR_LOG"
        rm -f "$PID_FILE"
        return 1
    fi
}

do_stop() {
    if ! _is_running; then
        echo "未在运行"
        rm -f "$PID_FILE"
        return 0
    fi

    local pid
    pid="$(cat "$PID_FILE")"
    echo "停止 PDD Crawler Web (PID $pid) ..."
    kill "$pid" 2>/dev/null || true

    # 等待最多 10 秒
    local i=0
    while [ $i -lt 10 ] && kill -0 "$pid" 2>/dev/null; do
        sleep 1
        i=$((i + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo "强制终止 ..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$PID_FILE"
    echo "已停止"
}

do_status() {
    if _is_running; then
        echo "运行中 (PID $(cat "$PID_FILE"))"
    else
        echo "未运行"
        rm -f "$PID_FILE"
    fi
}

do_log() {
    if [ ! -f "$STDOUT_LOG" ]; then
        echo "暂无日志"
        return 0
    fi
    tail -f "$STDOUT_LOG" "$STDERR_LOG"
}

case "${1:-start}" in
    start)   do_start   ;;
    stop)    do_stop    ;;
    restart) do_stop; do_start ;;
    status)  do_status  ;;
    log)     do_log     ;;
    *)
        echo "用法: $0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac
