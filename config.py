"""
配置模块 —— 向后兼容 shim。

规范配置已统一到 apps.backend.config.Settings（单一可信源）。
本模块只重新导出 memory/ 与 knowledge/ 等辅助模块仍 import 的旧模块级常量，
避免仓库里存在两套默认值互相打架。不要再在本文件新增配置项。
"""
from apps.backend.config import settings

LLM_API_KEY = settings.kimi_api_key
LLM_BASE_URL = settings.kimi_base_url
LLM_MODEL = settings.kimi_model
LLM_MAX_TOKENS = settings.kimi_max_tokens
LLM_TEMPERATURE = settings.llm_temperature

CHROMA_PERSIST_DIR = settings.chroma_persist_dir
SHORT_TERM_MEMORY_MAX_TURNS = settings.short_term_memory_max_turns
LONG_TERM_MEMORY_TOP_K = settings.long_term_memory_top_k

MAX_ITERATIONS = settings.max_iterations
AGENT_TOOL_MODE = settings.agent_tool_mode
MCP_SERVER_CONFIG_JSON = settings.mcp_server_config_json
