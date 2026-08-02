"""对象存储抽象层。

过渡期使用 LocalStorageBackend（本地文件系统），
生产期可切换为 S3Backend / COSBackend，业务代码无需改动。
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

from apps.backend.config import settings


@runtime_checkable
class StorageBackend(Protocol):
    """对象存储统一接口。"""

    def put(self, key: str, data: bytes, content_type: str = "") -> str:
        """写入对象，返回可访问的 key 或 URL。"""
        ...

    def get(self, key: str) -> bytes:
        """读取对象内容。"""
        ...

    def delete(self, key: str) -> None:
        """删除对象。"""
        ...

    def exists(self, key: str) -> bool:
        """检查对象是否存在。"""
        ...

    def presigned_url(self, key: str, expires: int = 3600) -> str:
        """获取预签名 URL（过渡期返回本地路径）。"""
        ...


class LocalStorageBackend:
    """基于本地文件系统的对象存储。

    存储路径: {storage_dir}/{key前两段}/{key}
    例如 key="snapshots/abc123.html" → {storage_dir}/snapshots/abc123.html

    后续切换为 S3Backend / COSBackend 只需实现同样的接口。
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = Path(base_dir or settings.storage_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _full_path(self, key: str) -> Path:
        """将存储 key 映射到本地文件路径。"""
        # 防止路径穿越
        safe_key = key.replace("\\", "/").lstrip("/")
        parts = safe_key.split("/")
        # 限制每段不包含 .. 或绝对路径标记
        parts = [p for p in parts if p and p != ".."]
        return self._base_dir.joinpath(*parts)

    def put(self, key: str, data: bytes, content_type: str = "") -> str:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get(self, key: str) -> bytes:
        path = self._full_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Storage object not found: {key}")
        return path.read_bytes()

    def delete(self, key: str) -> None:
        path = self._full_path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._full_path(key).exists()

    def presigned_url(self, key: str, expires: int = 3600) -> str:
        # 过渡期返回本地文件路径；生产期返回带签名的 HTTP URL
        return str(self._full_path(key))


# ── 工厂 ──────────────────────────────────────────────

_storage_instance: StorageBackend | None = None


def get_storage() -> StorageBackend:
    """获取全局存储实例（单例）。"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = LocalStorageBackend()
    return _storage_instance


def reset_storage() -> None:
    """重置单例（测试用）。"""
    global _storage_instance
    _storage_instance = None


def content_hash(data: bytes) -> str:
    """计算内容的 SHA-256 哈希，用于去重和存储 key 生成。"""
    return hashlib.sha256(data).hexdigest()
