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

# 模型服务配置 (支持 OMP Gemini 3.8 Flash、私有化 Qwen2.5、以及 Harness 本地规则)
SUPPORTED_MODELS = [
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash (OMP 内置底座)", "provider": "gemini", "status": "ACTIVE"},
    {"id": "qwen2.5-32b", "name": "Qwen2.5-32B-Instruct (私有化一体机)", "provider": "vllm", "status": "READY"},
    {"id": "harness-local", "name": "FinAudit Harness 确定性纪律引擎", "provider": "local", "status": "READY"},
]
ACTIVE_MODEL_ID = os.getenv("ACTIVE_MODEL_ID", "gemini-3.8-flash")
LLM_MODEL_NAME = ACTIVE_MODEL_ID
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"
ACTIVE_PROVIDER = os.getenv("ACTIVE_PROVIDER", "gemini")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "AIzaSyBV8UNdJAZ5XSI8ap10LJP-7Cwidyub9WQ")
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://127.0.0.1:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
# 规则配置
CONFIDENCE_THRESHOLD_HIGH = 0.85
CONFIDENCE_THRESHOLD_MEDIUM = 0.60
FUZZY_MATCH_THRESHOLD = 0.80  # 证据模糊匹配阈值
