"""
Agentic Controller
Top-level orchestrator for SatQuery AI.
Coordinates: validation → planning → dispatch → fusion → trace.
"""
from __future__ import annotations
import logging
import uuid
from pathlib import Path

from app.agent.dispatcher import ToolDispatcher
from app.agent.planner import TaskPlanner
from app.agent.registry import ModelRegistry, get_registry
from app.agent.validator import ValidationError, validate_and_ingest
from app.fusion.evidence_fusion import fuse_and_build_evidence
from app.models.schemas import (
    EvidenceObject, ExecutionPlan, JobStatus, TaskType,
)
from app.preprocessing.geo_pipeline import GeoImage
from app.storage import trace_store

logger = logging.getLogger(__name__)


class AgentController:
    """
    Single entry point for processing a SatQuery AI query.
    Instantiated once at application startup.
    """

    def __init__(self):
        self.registry: ModelRegistry = get_registry()
        self.planner = TaskPlanner(self.registry)
        self.dispatcher = ToolDispatcher(self.registry)
        self._initialized = False

    async def initialize(self) -> None:
        """Load LLM orchestrator (lazy — only if GPU available)."""
        if self._initialized:
            return
        await trace_store.init_db()
        self.planner.load_llm()
        self._initialized = True
        logger.info("AgentController initialized")

    async def process_query(
        self,
        job_id: str,
        query: str,
        file_paths: dict[str, Path],   # {upload_id: absolute path}
        image_roles: dict[str, str],   # {upload_id: role string}
    ) -> EvidenceObject:
        """
        Full pipeline:
        1. Validate inputs
        2. Classify task + generate execution plan
        3. Dispatch tools
        4. Fuse evidence
        5. Persist trace
        6. Return EvidenceObject
        """
        try:
            # ── Step 1: Input Validation ──────────────────────────────────────
            await trace_store.update_job_status(job_id, JobStatus.VALIDATING, "Validating inputs...")

            # Quick task pre-classification for validation (rule-based, no LLM needed)
            pre_task = _preclassify_task(query, len(file_paths), image_roles)

            ingested = validate_and_ingest(file_paths, image_roles, pre_task)
            geo_images: dict[str, GeoImage] = {uid: g for uid, (g, _) in ingested.items()}
            input_metas = [m for _, m in ingested.values()]

            # ── Step 2: Task Planning ─────────────────────────────────────────
            await trace_store.update_job_status(job_id, JobStatus.PLANNING, "Generating execution plan...")

            plan: ExecutionPlan = self.planner.plan(query, input_metas, job_id)
            await trace_store.save_execution_plan(job_id, plan)

            # ── Step 3: Tool Dispatch ─────────────────────────────────────────
            await trace_store.update_job_status(
                job_id, JobStatus.RUNNING,
                f"Running {len(plan.tool_calls)} tool(s): {[tc.tool_key for tc in plan.tool_calls]}"
            )

            plan = self.dispatcher.execute(plan, geo_images, query)
            await trace_store.save_execution_plan(job_id, plan)

            # ── Step 4: Evidence Fusion ───────────────────────────────────────
            await trace_store.update_job_status(job_id, JobStatus.FUSING, "Fusing evidence...")

            evidence = fuse_and_build_evidence(plan, geo_images)

            # ── Step 5: Persist ───────────────────────────────────────────────
            await trace_store.save_evidence(job_id, evidence)
            await trace_store.update_job_status(job_id, JobStatus.COMPLETED, "Done")

            logger.info(
                f"Job {job_id} completed: task={plan.query.classified_task.value}, "
                f"confidence={evidence.confidence:.3f}, tools={evidence.models_used}"
            )
            return evidence

        except ValidationError as e:
            await trace_store.update_job_status(
                job_id, JobStatus.FAILED, "Validation failed", error=str(e)
            )
            raise

        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            await trace_store.update_job_status(
                job_id, JobStatus.FAILED, "Processing failed", error=str(e)
            )
            raise


def _preclassify_task(query: str, num_images: int, image_roles: dict[str, str]) -> TaskType:
    """
    Fast rule-based pre-classification used only for input validation gating.
    The LLM planner does the authoritative classification afterward.
    """
    roles = set(image_roles.values())
    has_sar = "SAR" in roles
    has_t1_t2 = "T1" in roles and "T2" in roles

    if num_images == 2 and has_sar:
        return TaskType.CROSS_MODAL_ANALYSIS
    if num_images == 2 or has_t1_t2:
        return TaskType.BITEMPORAL_CHANGE_DETECT
    return TaskType.SINGLE_VQA


# Singleton
_controller: AgentController | None = None


def get_controller() -> AgentController:
    global _controller
    if _controller is None:
        _controller = AgentController()
    return _controller
