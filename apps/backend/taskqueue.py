"""任务队列抽象层。

过渡期使用 SQLiteTaskQueue（基于 SQLite 的任务队列），
生产期可切换为 RedisTaskQueue (RQ)，业务代码无需改动。

设计要点:
  - claim 使用 BEGIN IMMEDIATE + UPDATE ... WHERE status='queued' RETURNING
    模拟 SELECT FOR UPDATE SKIP LOCKED，保证单 worker 场景下的任务领取原子性
  - lease_until 机制：worker 领取任务后获得租约，超时自动回收
  - idempotency_key：相同 key 的重复入队返回原 job_id
  - 短事务：每个操作独立提交，不持有长事务
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import Column, DateTime, Integer, String, Text, text
from sqlalchemy.orm import Session

from apps.backend.database import Base, engine, SessionLocal


# ── 数据库模型 ──────────────────────────────────────────

class TaskQueueItem(Base):
    """SQLite 任务队列表。"""
    __tablename__ = "task_queue"

    id: str = Column(String(64), primary_key=True)
    job_type: str = Column(String(64), index=True, nullable=False)
    payload_json: str = Column(Text, default="{}")
    status: str = Column(String(32), default="queued", index=True, nullable=False)
    # queued | claimed | completed | failed
    worker_id: str | None = Column(String(64), nullable=True)
    lease_until: datetime | None = Column(DateTime, nullable=True)
    attempt: int = Column(Integer, default=0)
    max_attempts: int = Column(Integer, default=3)
    idempotency_key: str | None = Column(String(128), nullable=True, index=True)
    result_json: str | None = Column(Text, nullable=True)
    error_code: str | None = Column(String(64), nullable=True)
    error_msg: str | None = Column(Text, nullable=True)
    created_at: datetime = Column(DateTime, default=datetime.utcnow)
    updated_at: datetime = Column(DateTime, default=datetime.utcnow)


# ── 数据类 ──────────────────────────────────────────────

@dataclass
class Job:
    """任务对象。"""
    id: str
    job_type: str
    payload: dict[str, Any]
    status: str
    worker_id: str | None
    attempt: int
    max_attempts: int
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_msg: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_model(cls, item: TaskQueueItem) -> Job:
        return cls(
            id=item.id,
            job_type=item.job_type,
            payload=json.loads(item.payload_json) if item.payload_json else {},
            status=item.status,
            worker_id=item.worker_id,
            attempt=item.attempt,
            max_attempts=item.max_attempts,
            result=json.loads(item.result_json) if item.result_json else None,
            error_code=item.error_code,
            error_msg=item.error_msg,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


# ── Protocol ─────────────────────────────────────────────

@runtime_checkable
class TaskQueue(Protocol):
    """任务队列统一接口。"""

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> str:
        """入队任务，返回 job_id。"""
        ...

    def claim(
        self,
        worker_id: str,
        job_types: list[str],
        *,
        lease_seconds: int = 300,
    ) -> Job | None:
        """领取一个任务（原子操作），返回 Job 或 None。"""
        ...

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        """标记任务完成。"""
        ...

    def fail(self, job_id: str, error_code: str, error_msg: str) -> None:
        """标记任务失败（或重试）。"""
        ...

    def release_expired_leases(self) -> int:
        """回收过期租约的任务，返回回收数量。"""
        ...

    def get_job(self, job_id: str) -> Job | None:
        """获取任务详情。"""
        ...


# ── SQLite 实现 ─────────────────────────────────────────

class SQLiteTaskQueue:
    """基于 SQLite 的任务队列实现。

    使用 BEGIN IMMEDIATE + UPDATE ... WHERE ... RETURNING
    模拟 SELECT FOR UPDATE SKIP LOCKED。
    """

    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    def _new_id(self) -> str:
        return uuid.uuid4().hex

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
        max_attempts: int = 3,
    ) -> str:
        # 幂等检查：相同 idempotency_key 的非终态任务直接返回原 job_id
        if idempotency_key:
            with self._session_factory() as session:
                existing = (
                    session.query(TaskQueueItem)
                    .filter(
                        TaskQueueItem.idempotency_key == idempotency_key,
                        TaskQueueItem.status.in_(["queued", "claimed", "completed"]),
                    )
                    .first()
                )
                if existing:
                    return existing.id

        job_id = self._new_id()
        item = TaskQueueItem(
            id=job_id,
            job_type=job_type,
            payload_json=json.dumps(payload, ensure_ascii=False, default=str),
            status="queued",
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
        )
        with self._session_factory() as session:
            session.add(item)
            session.commit()
        return job_id

    def claim(
        self,
        worker_id: str,
        job_types: list[str],
        *,
        lease_seconds: int = 300,
    ) -> Job | None:
        """原子领取一个 queued 任务。

        用 BEGIN IMMEDIATE 获取写锁，然后 UPDATE ... WHERE status='queued'
        LIMIT 1，再 SELECT 返回。SQLite 不支持 RETURNING，所以分两步。
        """
        now = datetime.utcnow()
        lease_until = now + timedelta(seconds=lease_seconds)

        with self._session_factory() as session:
            # BEGIN IMMEDIATE 获取写锁
            session.execute(text("BEGIN IMMEDIATE"))

            # 找到一个 queued 任务
            item = (
                session.query(TaskQueueItem)
                .filter(
                    TaskQueueItem.status == "queued",
                    TaskQueueItem.job_type.in_(job_types),
                )
                .order_by(TaskQueueItem.created_at)
                .first()
            )

            if item is None:
                session.rollback()
                return None

            # 领取任务
            item.status = "claimed"
            item.worker_id = worker_id
            item.lease_until = lease_until
            item.attempt = item.attempt + 1
            item.updated_at = now
            session.commit()

            return Job.from_model(item)

    def complete(self, job_id: str, result: dict[str, Any]) -> None:
        with self._session_factory() as session:
            item = session.query(TaskQueueItem).filter(TaskQueueItem.id == job_id).first()
            if item is None:
                raise KeyError(f"Job not found: {job_id}")
            item.status = "completed"
            item.result_json = json.dumps(result, ensure_ascii=False, default=str)
            item.updated_at = datetime.utcnow()
            session.commit()

    def fail(self, job_id: str, error_code: str, error_msg: str) -> None:
        with self._session_factory() as session:
            item = session.query(TaskQueueItem).filter(TaskQueueItem.id == job_id).first()
            if item is None:
                raise KeyError(f"Job not found: {job_id}")

            # 如果还有重试次数，重新入队；否则标记失败
            if item.attempt < item.max_attempts:
                item.status = "queued"
                item.worker_id = None
                item.lease_until = None
            else:
                item.status = "failed"

            item.error_code = error_code
            item.error_msg = error_msg
            item.updated_at = datetime.utcnow()
            session.commit()

    def release_expired_leases(self) -> int:
        """回收过期租约的任务，将其重新置为 queued。"""
        now = datetime.utcnow()
        with self._session_factory() as session:
            items = (
                session.query(TaskQueueItem)
                .filter(
                    TaskQueueItem.status == "claimed",
                    TaskQueueItem.lease_until < now,
                )
                .all()
            )
            for item in items:
                # 检查是否还有重试次数
                if item.attempt < item.max_attempts:
                    item.status = "queued"
                else:
                    item.status = "failed"
                item.worker_id = None
                item.lease_until = None
                item.updated_at = now
            session.commit()
            return len(items)

    def get_job(self, job_id: str) -> Job | None:
        with self._session_factory() as session:
            item = session.query(TaskQueueItem).filter(TaskQueueItem.id == job_id).first()
            return Job.from_model(item) if item else None

    def count_by_status(self, status: str) -> int:
        """获取指定状态的任务数量（监控用）。"""
        with self._session_factory() as session:
            return (
                session.query(TaskQueueItem)
                .filter(TaskQueueItem.status == status)
                .count()
            )


# ── 工厂 ─────────────────────────────────────────────────

_queue_instance: TaskQueue | None = None


def get_task_queue() -> TaskQueue:
    """获取全局任务队列实例（单例）。"""
    global _queue_instance
    if _queue_instance is None:
        _queue_instance = SQLiteTaskQueue()
    return _queue_instance


def reset_task_queue() -> None:
    """重置单例（测试用）。"""
    global _queue_instance
    _queue_instance = None
