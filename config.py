
import os
from dotenv import load_dotenv

load_dotenv()

# LLM Configuration
LLM_CONFIG = {
    "api_key": os.environ["LLM_API_KEY"],
    "model_name": os.getenv("LLM_MODEL_NAME", "deepseek-v4-pro"),
    "base_url": os.getenv("LLM_BASE_URL", "https://api.deepseek.com"),
    "temperature": 0.7,
    "max_tokens": 2048,
}

# System Configuration
SYSTEM_CONFIG = {
    "enable_llm": True,  # Set to True to use LLM (recommended), False for rule-based
    "log_level": "INFO",
    "max_retries": 3,
    "timeout": 60,  # Increased timeout for better stability
}

# RAG 知识库：嵌入模型（硅基流动 API）
RAG_CONFIG = {
    "embedding_model": "BAAI/bge-large-zh-v1.5",
    "embedding_api_url": "https://api.siliconflow.cn/v1/embeddings",
    "embedding_api_key": os.environ.get("SILICONFLOW_API_KEY", ""),
    "embedding_dim": 1024,
}

# 连接与可用性：重试、熔断、健康检查
RESILIENCE_CONFIG = {
    "max_retries": 3,              # 单次请求最大重试次数（与 SYSTEM_CONFIG 对齐）
    "retry_base_delay_sec": 1.0,   # 重试退避基数（秒）
    "retry_max_delay_sec": 30.0,   # 重试退避上限（秒）
    "circuit_failure_threshold": 5, # 连续失败多少次后熔断
    "circuit_recovery_timeout_sec": 60.0,  # 熔断后多少秒进入半开
    "circuit_half_open_successes": 2,      # 半开状态下连续成功多少次后关闭
    "health_check_timeout_sec": 10.0,      # 健康检查请求超时（秒）
}
