"""
Execution Trace Store
Persists every job's execution plan, status, and evidence to SQLite.
Provides auditable trace for every query processed by SatQuery AI.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text, select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings
from app.models.schemas import EvidenceObject, ExecutionPlan, JobStatus

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"

    job_id = Column(String, primary_key=True)
    status = Column(String, default=JobStatus.PENDING.value)
    progress_message = Column(String, default="")
    query = Column(Text, default="")
    execution_plan_json = Column(Text, nullable=True)
    evidence_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def create_job(job_id: str, query: str) -> None:
    async with AsyncSessionLocal() as session:
        record = JobRecord(
            job_id=job_id,
            status=JobStatus.PENDING.value,
            query=query,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(record)
        await session.commit()


async def update_job_status(
    job_id: str,
    status: JobStatus,
    progress_message: str = "",
    error: str | None = None,
) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(JobRecord)
            .where(JobRecord.job_id == job_id)
            .values(
                status=status.value,
                progress_message=progress_message,
                error=error,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()


async def save_execution_plan(job_id: str, plan: ExecutionPlan) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(JobRecord)
            .where(JobRecord.job_id == job_id)
            .values(
                execution_plan_json=plan.model_dump_json(),
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()


async def save_evidence(job_id: str, evidence: EvidenceObject) -> None:
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(JobRecord)
            .where(JobRecord.job_id == job_id)
            .values(
                evidence_json=evidence.model_dump_json(),
                status=JobStatus.COMPLETED.value,
                updated_at=datetime.utcnow(),
            )
        )
        await session.commit()


async def get_job(job_id: str) -> JobRecord | None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(JobRecord).where(JobRecord.job_id == job_id))
        return result.scalar_one_or_none()


async def get_job_status(job_id: str) -> dict | None:
    record = await get_job(job_id)
    if not record:
        return None
    return {
        "job_id": record.job_id,
        "status": record.status,
        "progress_message": record.progress_message,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }


async def get_job_result(job_id: str) -> dict | None:
    record = await get_job(job_id)
    if not record:
        return None
    evidence = None
    if record.evidence_json:
        evidence = EvidenceObject.model_validate_json(record.evidence_json)
    return {
        "job_id": record.job_id,
        "status": record.status,
        "evidence": evidence,
        "error": record.error,
    }


async def get_job_trace(job_id: str) -> dict | None:
    record = await get_job(job_id)
    if not record:
        return None
    plan = None
    if record.execution_plan_json:
        plan = ExecutionPlan.model_validate_json(record.execution_plan_json)
    return {
        "job_id": record.job_id,
        "query": record.query,
        "status": record.status,
        "execution_plan": plan.model_dump() if plan else None,
        "created_at": record.created_at.isoformat() if record.created_at else "",
        "updated_at": record.updated_at.isoformat() if record.updated_at else "",
    }
