import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

# 知识库配置
KNOWLEDGE_PATH = BASE_DIR / "config/knowledge"

# 模型服务配置
OLLAMA_CONFIG = {
    "base_url": os.getenv("OLLAMA_URL", "http://127.0.0.1:11439/api"),
    "timeout": 15,
    "default_model": "DeepSeek-R1-Distill-Qwen-1.5B",
    "generation_params": {
        "temperature": 0.3,
        "num_predict": 500
    }
}
