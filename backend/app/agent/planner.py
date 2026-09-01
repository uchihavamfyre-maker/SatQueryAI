"""
Query Understanding + Task Planner
The LLM acts as orchestrator only — it classifies the task and generates
a structured ExecutionPlan. It does NOT touch image data.
The LLM is constrained to select only tools from the registry.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

from app.agent.registry import ModelRegistry
from app.models.schemas import (
    AgentConstraints, ExecutionPlan, InputMetadata, InputModality,
    InputRole, QueryInfo, TaskType, ToolCall, ToolCallStatus,
)

logger = logging.getLogger(__name__)

# ─── System Prompt Template ───────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are the task planner for SatQuery AI, a remote-sensing image analysis system.

Your ONLY job is to:
1. Classify the user's query into one task type.
2. Select the appropriate tools from the registry below.
3. Output a valid JSON execution plan.

TASK TYPES:
- SINGLE_VQA: User asks a question about a single image (e.g., "What land cover is this?")
- SINGLE_CAPTION: User asks for a description/caption of a single image
- SINGLE_GROUNDING: User asks to locate/find a region in a single image
- BITEMPORAL_CHANGE_DETECT: User asks what changed between two images
- BITEMPORAL_CHANGE_VQA: User asks a specific question about changes between two images
- CROSS_MODAL_ANALYSIS: User has optical + SAR images and asks for joint analysis

AVAILABLE TOOLS (registry):
{registry_summary}

RULES:
- You MUST output ONLY valid JSON matching the schema below.
- You MUST NOT invent tools not in the registry.
- You MUST NOT execute code.
- You MUST NOT describe image content yourself.
- Select the MINIMUM set of tools needed.
- For SINGLE_GROUNDING, always include RS_GROUNDING_FALLBACK after RS_GROUNDING.
- For CROSS_MODAL_ANALYSIS, always include SAR_PREPROCESS before OPTICAL_SAR_ANALYZER.
- For BITEMPORAL tasks, always include CHANGE_DETECTION. Add CHANGE_VQA if a question is asked, else CHANGE_CAPTION.

OUTPUT SCHEMA:
{{
  "classified_task": "<TASK_TYPE>",
  "task_confidence": <float 0-1>,
  "task_rationale": "<one sentence>",
  "tool_keys": ["<TOOL_KEY>", ...],
  "tool_parameters": {{
    "<TOOL_KEY>": {{<param_name>: <value>, ...}}
  }}
}}
"""

_USER_PROMPT = """Query: "{query}"
Number of images: {num_images}
Image modalities: {modalities}
Image roles: {roles}

Output the JSON execution plan:"""


# ─── Planner ─────────────────────────────────────────────────────────────────

class TaskPlanner:
    """
    Uses an LLM to classify the query and generate an execution plan.
    Falls back to a rule-based planner if the LLM is unavailable.
    """

    def __init__(self, registry: ModelRegistry):
        self.registry = registry
        self._llm = None
        self._tokenizer = None
        self._llm_available = False

    def load_llm(self) -> None:
        """Skip LLM loading — use fast rule-based planner (no GPU required)."""
        self._llm_available = False
        logger.info("Using rule-based planner (LLM disabled — no GPU detected).")

    def plan(
        self,
        query: str,
        input_metas: list[InputMetadata],
        job_id: str,
    ) -> ExecutionPlan:
        """
        Generate an ExecutionPlan for the given query and inputs.
        Tries LLM first; falls back to rule-based planner.
        """
        modalities = [m.modality.value for m in input_metas]
        roles = [m.role.value for m in input_metas]

        if self._llm_available:
            plan_dict = self._llm_plan(query, len(input_metas), modalities, roles)
        else:
            plan_dict = self._rule_based_plan(query, input_metas)

        return self._build_execution_plan(plan_dict, query, input_metas, job_id)

    def _llm_plan(
        self,
        query: str,
        num_images: int,
        modalities: list[str],
        roles: list[str],
    ) -> dict[str, Any]:
        import torch

        registry_summary = json.dumps(self.registry.agent_summary(), indent=2)
        system = _SYSTEM_PROMPT.format(registry_summary=registry_summary)
        user = _USER_PROMPT.format(
            query=query,
            num_images=num_images,
            modalities=", ".join(modalities),
            roles=", ".join(roles),
        )

        # Mistral instruction format
        prompt = f"[INST] {system}\n\n{user} [/INST]"
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._llm.device)

        with torch.no_grad():
            output_ids = self._llm.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        raw = self._tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        return self._parse_llm_output(raw)

    def _parse_llm_output(self, raw: str) -> dict[str, Any]:
        """Extract JSON from LLM output, handling markdown code blocks."""
        # Strip markdown code fences
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        # Find first { ... } block
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            logger.warning("LLM output contained no JSON. Falling back to rule-based.")
            return {}
        try:
            parsed = json.loads(match.group())
            # Validate tool keys against registry
            valid_keys = set(self.registry.keys())
            parsed["tool_keys"] = [k for k in parsed.get("tool_keys", []) if k in valid_keys]
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"LLM JSON parse error: {e}. Falling back.")
            return {}

    def _rule_based_plan(
        self,
        query: str,
        input_metas: list[InputMetadata],
    ) -> dict[str, Any]:
        """
        Deterministic fallback planner based on image count, modality, and query keywords.
        Used when LLM is unavailable or produces invalid output.
        """
        q = query.lower()
        num = len(input_metas)
        modalities = {m.modality for m in input_metas}
        has_sar = InputModality.SAR in modalities

        # Cross-modal: 2 images, one SAR
        if num == 2 and has_sar:
            return {
                "classified_task": TaskType.CROSS_MODAL_ANALYSIS.value,
                "task_confidence": 0.9,
                "task_rationale": "Two images detected with SAR modality — cross-modal analysis.",
                "tool_keys": ["SAR_PREPROCESS", "OPTICAL_SAR_ANALYZER"],
                "tool_parameters": {},
            }

        # Bi-temporal: 2 optical images
        if num == 2:
            is_vqa = any(w in q for w in ["how many", "did", "has", "is there", "what percentage", "count"])
            task = TaskType.BITEMPORAL_CHANGE_VQA if is_vqa else TaskType.BITEMPORAL_CHANGE_DETECT
            tools = ["CHANGE_DETECTION", "CHANGE_VQA" if is_vqa else "CHANGE_CAPTION"]
            return {
                "classified_task": task.value,
                "task_confidence": 0.85,
                "task_rationale": "Two optical images — bi-temporal change analysis.",
                "tool_keys": tools,
                "tool_parameters": {},
            }

        # Single image
        is_grounding = any(w in q for w in ["locate", "find", "where", "show me", "highlight", "identify region"])
        is_caption = any(w in q for w in ["describe", "caption", "what is in", "scene", "overview"])

        if is_grounding:
            return {
                "classified_task": TaskType.SINGLE_GROUNDING.value,
                "task_confidence": 0.85,
                "task_rationale": "Grounding keywords detected.",
                "tool_keys": ["RS_GROUNDING", "RS_GROUNDING_FALLBACK"],
                "tool_parameters": {},
            }
        if is_caption:
            return {
                "classified_task": TaskType.SINGLE_CAPTION.value,
                "task_confidence": 0.85,
                "task_rationale": "Caption/description keywords detected.",
                "tool_keys": ["RS_CAPTION"],
                "tool_parameters": {},
            }
        # Default: VQA
        return {
            "classified_task": TaskType.SINGLE_VQA.value,
            "task_confidence": 0.75,
            "task_rationale": "Default: single-image VQA.",
            "tool_keys": ["RS_VQA"],
            "tool_parameters": {},
        }

    def _build_execution_plan(
        self,
        plan_dict: dict[str, Any],
        query: str,
        input_metas: list[InputMetadata],
        job_id: str,
    ) -> ExecutionPlan:
        if not plan_dict:
            plan_dict = self._rule_based_plan(query, input_metas)

        task_str = plan_dict.get("classified_task", TaskType.SINGLE_VQA.value)
        try:
            task = TaskType(task_str)
        except ValueError:
            task = TaskType.SINGLE_VQA

        tool_keys = plan_dict.get("tool_keys", [])
        tool_params = plan_dict.get("tool_parameters", {})
        enabled_keys = {t.key for t in self.registry.all_enabled()}

        tool_calls = []
        for key in tool_keys:
            if key not in enabled_keys:
                logger.warning(f"Planner selected disabled/unknown tool '{key}' — skipping.")
                continue
            desc = self.registry.get(key)
            params = tool_params.get(key, {})
            # Merge with defaults
            merged_params = {**desc.default_parameters(), **params}
            tool_calls.append(ToolCall(
                tool_key=key,
                model_name=desc.model_name,
                model_version=desc.model_version,
                input_artifacts=[m.input_id for m in input_metas],
                parameters=merged_params,
                permitted_parameters=desc.permitted_param_names(),
                status=ToolCallStatus.PENDING,
            ))

        return ExecutionPlan(
            job_id=job_id,
            query=QueryInfo(
                raw_text=query,
                classified_task=task,
                task_confidence=plan_dict.get("task_confidence", 0.0),
                task_rationale=plan_dict.get("task_rationale", ""),
            ),
            inputs=input_metas,
            tool_calls=tool_calls,
            constraints=AgentConstraints(
                llm_may_invoke_tools=tool_keys,
                llm_may_not_execute_code=True,
                llm_may_not_invent_tools=True,
            ),
        )
