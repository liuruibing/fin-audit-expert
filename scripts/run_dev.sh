#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=================================================="
echo "  启动 FinAudit 审核专家系统 (本地开发模式)  "
echo "=================================================="

export PYTHONPATH=.

PYTHON_BIN="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_BIN=".venv/bin/python"
fi

echo "[+] 启动 FastAPI Web 审核工作台服务..."
echo "[+] 访问地址: http://127.0.0.1:8090"
$PYTHON_BIN -m uvicorn backend.main:app --host 127.0.0.1 --port 8090 --reload
