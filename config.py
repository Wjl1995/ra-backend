"""
ReAct Agent 配置文件
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM 配置 ──────────────────────────────────────────────
LLM_API_KEY = os.getenv("KIMI_API_KEY", "")
LLM_BASE_URL = os.getenv("KIMI_BASE_URL", "https://api.moonshot.cn/v1")
LLM_MODEL = os.getenv("KIMI_MODEL", "moonshot-v1-8k")
LLM_MAX_TOKENS = 2048
LLM_TEMPERATURE = 0.7

# ── Memory 配置 ───────────────────────────────────────────
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
SHORT_TERM_MEMORY_MAX_TURNS = 10   # 短期记忆保留最近 N 轮对话
LONG_TERM_MEMORY_TOP_K = 5         # 长期记忆检索返回 Top K 条

# ── ReAct Agent 配置 ──────────────────────────────────────
MAX_ITERATIONS = 10                  # 最大推理-行动轮次
