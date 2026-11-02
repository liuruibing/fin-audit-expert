#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=================================================="
echo "  启动 FinAudit 审核专家系统 (本地开发模式)  "
echo "=================================================="

export PYTHONPATH=.

# 检查依赖
python3 -c "import fastapi, uvicorn" 2>/dev/null || {
    echo "[!] 正在安装基础依赖..."
    pip3 install -r requirements.txt
}

echo "[+] 启动 FastAPI Web 审核工作台服务..."
echo "[+] 访问地址: http://127.0.0.1:8080"
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8080 --reload
