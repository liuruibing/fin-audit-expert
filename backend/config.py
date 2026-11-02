import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "backend" / "data"
SAMPLES_DIR = DATA_DIR / "samples"
GOLDEN_BENCHMARK_PATH = DATA_DIR / "golden_benchmark.json"
DECISION_LOG_PATH = DATA_DIR / "decision_log.json"

# 确保目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# 模型服务配置 (直接接入本地 OMP 代理网关 8317 上的真实 Gemini Flash 模型)
SUPPORTED_MODELS = [
    {"id": "gemini-3-flash", "name": "Gemini 3.8/3 Flash (OMP 真实大模型)", "provider": "gemini", "status": "ACTIVE"},
    {"id": "qwen2.5-32b", "name": "Qwen2.5-32B-Instruct (私有化一体机)", "provider": "vllm", "status": "READY"},
    {"id": "harness-local", "name": "FinAudit Harness 确定性纪律引擎", "provider": "local", "status": "READY"},
]
ACTIVE_MODEL_ID = os.getenv("ACTIVE_MODEL_ID", "gemini-3-flash")
LLM_MODEL_NAME = ACTIVE_MODEL_ID
DEFAULT_GEMINI_MODEL = "gemini-3-flash"
ACTIVE_PROVIDER = os.getenv("ACTIVE_PROVIDER", "gemini")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyBV8UNdJAZ5XSI8ap10LJP-7Cwidyub9WQ")
# 本地 OMP 代理网关 (直接支持流式与自然语言对话)
LOCAL_GATEWAY_URL = "http://127.0.0.1:8317/v1"
LOCAL_GATEWAY_KEY = "sk-Pg1qzNeHB6oIp2Ekm"

LLM_API_BASE = os.getenv("LLM_API_BASE", LOCAL_GATEWAY_URL)
LLM_API_KEY = os.getenv("LLM_API_KEY", LOCAL_GATEWAY_KEY)
# 规则配置
CONFIDENCE_THRESHOLD_HIGH = 0.85
CONFIDENCE_THRESHOLD_MEDIUM = 0.60
FUZZY_MATCH_THRESHOLD = 0.80  # 证据模糊匹配阈值
