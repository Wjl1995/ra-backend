"""
embedding_service —— 统一文本向量化服务

线上（ra-backend-app 容器）已具备 onnxruntime + tokenizers + numpy，默认加载
量化 ONNX 多语言句向量模型（Xenova/paraphrase-multilingual-MiniLM-L12-v2，维度 384，
中文友好）。当模型目录缺失或依赖不可用时，自动降级为基于哈希的词袋向量（零依赖），
语义能力弱，但保证服务不崩、检索仍可用。

调用方应始终通过 get_embedding_service() 获取单例，避免重复加载模型（加载约 1~2s）。
"""
from __future__ import annotations

import hashlib
import logging
import os
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__), "..", "..", "..",
        "models", "embedding", "Xenova_paraphrase-multilingual-MiniLM-L12-v2",
    )
)

EMBED_DIM = 384


class HashEmbeddingFunction:
    """零依赖降级：N-gram + 词级哈希词袋（弱语义，仅兜底面）"""

    def __init__(self, dim: int = EMBED_DIM, n_grams: int = 3):
        self.dim = dim
        self.n_grams = n_grams

    def _vec(self, text: str) -> List[float]:
        vec = np.zeros(self.dim, dtype=np.float32)
        for i in range(len(text) - self.n_grams + 1):
            gram = text[i:i + self.n_grams]
            idx = int(hashlib.md5(gram.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        for word in text.split():
            idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]


class OnnxEmbeddingFunction:
    """ONNX Runtime 推理的多语言句向量（mean pooling + L2 归一化）"""

    def __init__(self, model_dir: str, quantize: bool = True):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        tok_path = os.path.join(model_dir, "tokenizer.json")
        if not os.path.exists(tok_path):
            raise FileNotFoundError(f"tokenizer.json not found in {model_dir}")
        self.tokenizer = Tokenizer.from_file(tok_path)
        self.tokenizer.enable_truncation(max_length=256)

        onnx_name = "onnx/model_quantized.onnx" if quantize else "onnx/model.onnx"
        model_path = os.path.join(model_dir, onnx_name)
        if not os.path.exists(model_path):
            model_path = os.path.join(model_dir, "onnx/model.onnx")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model not found in {model_dir}/onnx")

        self.session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.output_names = [o.name for o in self.session.get_outputs()]

    def _encode(self, text: str) -> List[int]:
        enc = self.tokenizer.encode(text)
        ids = enc.ids
        return ids if ids else [0]

    def embed(self, texts: List[str]) -> List[List[float]]:
        all_ids = [self._encode(t) for t in texts]
        max_len = max(len(x) for x in all_ids)
        input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
        attn = np.zeros((len(texts), max_len), dtype=np.int64)
        for i, ids in enumerate(all_ids):
            input_ids[i, :len(ids)] = ids
            attn[i, :len(ids)] = 1

        feeds = {"input_ids": input_ids}
        if "attention_mask" in self.input_names:
            feeds["attention_mask"] = attn
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.zeros((len(texts), max_len), dtype=np.int64)

        outputs = self.session.run(self.output_names, feeds)
        out_map = dict(zip(self.output_names, outputs))
        last_hidden = out_map.get("last_hidden_state", outputs[0])

        mask_f = attn.astype(np.float32)
        summed = np.sum(last_hidden * mask_f[:, :, None], axis=1)
        counts = np.maximum(np.sum(mask_f, axis=1, keepdims=True), 1.0)
        pooled = summed / counts
        norms = np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
        normed = pooled / norms
        return normed.astype(np.float32).tolist()


class EmbeddingService:
    """统一向量化入口：优先 ONNX 真模型，失败降级 hash。"""

    def __init__(self, model_dir: str = DEFAULT_MODEL_DIR, force_hash: bool = False):
        self.backend = "hash"
        self._fn = None
        if not force_hash:
            try:
                self._fn = OnnxEmbeddingFunction(model_dir)
                self.backend = "onnx"
                logger.info("EmbeddingService: ONNX backend ready (%s)", model_dir)
            except Exception as e:
                logger.warning("EmbeddingService: ONNX init failed (%s); hash fallback", e)
        if self._fn is None:
            self._fn = HashEmbeddingFunction()
            logger.warning("EmbeddingService: using HASH fallback backend")

    @property
    def dim(self) -> int:
        return EMBED_DIM

    def embed(self, texts: List[str]) -> List[List[float]]:
        return self._fn.embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self.embed([text])[0]


_EMBEDDING_SERVICE: Optional[EmbeddingService] = None


def get_embedding_service() -> EmbeddingService:
    """懒加载单例，模型只加载一次。"""
    global _EMBEDDING_SERVICE
    if _EMBEDDING_SERVICE is None:
        _EMBEDDING_SERVICE = EmbeddingService()
    return _EMBEDDING_SERVICE
