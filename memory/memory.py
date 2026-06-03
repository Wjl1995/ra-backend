"""
Memory 模块 —— 支持短期记忆 + 长期向量记忆

短期记忆：基于列表的对话窗口，保留最近 N 轮
长期记忆：基于 ChromaDB 的向量检索，持久化存储

注意：由于沙箱环境限制 ONNX 线程池，默认使用自定义 embedding 函数。
生产环境可切换为 OpenAI/Moonshot embedding API 或 sentence-transformers。
"""
from __future__ import annotations

import hashlib
import json
import numpy as np
import uuid
from datetime import datetime
from typing import Optional

import chromadb
from chromadb.api.types import EmbeddingFunction
from config import CHROMA_PERSIST_DIR, SHORT_TERM_MEMORY_MAX_TURNS, LONG_TERM_MEMORY_TOP_K, LLM_API_KEY, LLM_BASE_URL


# ─── 短期记忆 ────────────────────────────────────────────────

class ShortTermMemory:
    """滑动窗口式短期记忆，保留最近 N 轮对话"""

    def __init__(self, max_turns: int = SHORT_TERM_MEMORY_MAX_TURNS):
        self.max_turns = max_turns
        self.messages: list[dict] = []

    def add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_turns * 2:  # 每轮 = user + assistant
            self.messages = self.messages[-(self.max_turns * 2):]

    def get(self) -> list[dict]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()

    def format_for_prompt(self) -> str:
        """格式化为可插入 prompt 的文本"""
        lines = []
        for msg in self.messages:
            role = msg["role"].upper()
            lines.append(f"[{role}]: {msg['content']}")
        return "\n".join(lines)


# ─── Embedding 函数 ──────────────────────────────────────────

class HashEmbeddingFunction(EmbeddingFunction):
    """
    基于哈希的轻量 Embedding 函数（无需 ONNX/GPU）

    原理：对文本做 N-gram 哈希 → 映射到固定维度向量
    优点：零依赖、启动快、沙箱安全
    缺点：语义理解能力弱于 Transformer 模型

    如需更好的语义检索，可替换为：
    - OpenAIEmbeddingFunction（使用 Kimi/OpenAI API）
    - SentenceTransformerEmbeddingFunction（本地模型）
    """

    def __init__(self, dim: int = 384, n_grams: int = 3):
        self.dim = dim
        self.n_grams = n_grams

    def _text_to_vector(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        # 字符级 n-gram
        for i in range(len(text) - self.n_grams + 1):
            gram = text[i:i + self.n_grams]
            idx = int(hashlib.md5(gram.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        # 词级哈希
        for word in text.split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        # L2 归一化
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._text_to_vector(text) for text in input]


def create_embedding_function(mode: str = "hash") -> EmbeddingFunction:
    """
    创建 Embedding 函数

    Args:
        mode: "hash" 使用内置哈希 embedding（零依赖）
              "openai" 使用 OpenAI 兼容 API（需配置 API Key）
    """
    if mode == "openai":
        from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
        return OpenAIEmbeddingFunction(
            api_key=LLM_API_KEY,
            api_base=LLM_BASE_URL,
            model_name="text-embedding-v3",  # Moonshot embedding model
        )
    return HashEmbeddingFunction()


# ─── 长期记忆 ────────────────────────────────────────────────

class LongTermMemory:
    """基于 ChromaDB 的长期向量记忆，支持语义检索"""

    def __init__(
        self,
        persist_dir: str = CHROMA_PERSIST_DIR,
        collection_name: str = "agent_memory",
        embedding_mode: str = "hash",
    ):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding_fn = create_embedding_function(embedding_mode)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        text: str,
        metadata: Optional[dict] = None,
        doc_id: Optional[str] = None,
    ) -> str:
        """存入一条记忆"""
        doc_id = doc_id or str(uuid.uuid4())
        meta = metadata or {}
        meta["timestamp"] = datetime.now().isoformat()
        self.collection.upsert(
            ids=[doc_id],
            documents=[text],
            metadatas=[meta],
        )
        return doc_id

    def search(self, query: str, top_k: int = LONG_TERM_MEMORY_TOP_K) -> list[dict]:
        """语义检索相关记忆"""
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, self.collection.count() or 1),
        )
        memories = []
        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                memories.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": dist,
                })
        return memories

    def delete(self, doc_id: str) -> None:
        self.collection.delete(ids=[doc_id])

    def count(self) -> int:
        return self.collection.count()


# ─── 统一记忆管理 ────────────────────────────────────────────

class AgentMemory:
    """
    统一记忆管理器
    - 短期记忆：当前对话上下文
    - 长期记忆：跨会话持久化知识
    - 自动将重要信息存入长期记忆
    """

    def __init__(self):
        self.short_term = ShortTermMemory()
        self.long_term = LongTermMemory()
        self._pending_user_message: Optional[str] = None  # 暂存用户消息，等待助手回复

    def add_user_message(self, content: str) -> None:
        self.short_term.add("user", content)
        # 暂存用户消息，等待助手回复后合并存储
        self._pending_user_message = content

    def add_assistant_message(self, content: str) -> None:
        self.short_term.add("assistant", content)
        # 如果有待处理的用户消息，合并存储到长期记忆
        if self._pending_user_message:
            user_summary = self._simple_summarize(self._pending_user_message, max_length=100)
            assistant_summary = self._simple_summarize(content, max_length=150)
            combined_text = f"用户: {user_summary}\n助手: {assistant_summary}"
            self.long_term.add(combined_text, {"type": "conversation_round"})
            self._pending_user_message = None  # 清空暂存

    def _simple_summarize(self, text: str, max_length: int = 100) -> str:
        """简单摘要：截取开头+结尾，中间用省略号"""
        if len(text) <= max_length:
            return text
        # 取前面 2/3，后面 1/3
        part1_len = int(max_length * 0.7)
        part2_len = max_length - part1_len - 3  # 3 是省略号
        return text[:part1_len] + "..." + text[-part2_len:] if part2_len > 0 else text[:max_length] + "..."

    def save_to_long_term(self, text: str, metadata: Optional[dict] = None) -> str:
        """主动保存重要信息到长期记忆"""
        return self.long_term.add(text, metadata)

    def recall(self, query: str, top_k: int = LONG_TERM_MEMORY_TOP_K) -> str:
        """从长期记忆中检索相关信息，返回格式化文本"""
        results = self.long_term.search(query, top_k)
        if not results:
            return "（无相关长期记忆）"
        lines = []
        for i, r in enumerate(results, 1):
            ts = r["metadata"].get("timestamp", "unknown")
            lines.append(f"  {i}. [{ts}] {r['text']} (相似度: {1 - r['distance']:.2f})")
        return "\n".join(lines)

    def get_context_messages(self) -> list[dict]:
        """获取用于 LLM 调用的消息列表"""
        return self.short_term.get()

    def reset_conversation(self) -> None:
        """重置短期记忆（开始新对话）"""
        self.short_term.clear()
