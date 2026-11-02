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

# 模型服务配置 (支持本地 vLLM / Ollama 或云端 API)
LLM_API_BASE = os.getenv("LLM_API_BASE", "http://127.0.0.1:8000/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "EMPTY")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "Qwen2.5-32B-Instruct")

# 规则配置
CONFIDENCE_THRESHOLD_HIGH = 0.85
CONFIDENCE_THRESHOLD_MEDIUM = 0.60
FUZZY_MATCH_THRESHOLD = 0.80  # 证据模糊匹配阈值
