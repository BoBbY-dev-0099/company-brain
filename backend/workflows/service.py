"""Evidence -> memory -> live context -> safe action workflow service."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from backend.brain import store as brain_store
from backend.config import settings
from backend.core import compiler
from backend.core.sag_evaluator import SagRuleError, evaluate_rule
from backend.core.schema import CompanyBrainSkill, RawEvent
from backend.workflows.models import (
    DecisionBrief,
    DecisionFact,
    DecisionInference,
    EvidenceAvailability,
    EvidenceFreshness,
    EvidenceInput,
    EvidenceRecord,
    MemoryReference,
    MissingEvidence,
    WorkflowOutcome,
    WorkflowOutcomeRequest,
    WorkflowRun,
    WorkflowRunRequest,
    WorkflowRunStatus,
    WorkflowTemplate,
    WorkflowVerdict,
    workflow_now,
)
from backend.workflows.store import WorkflowRepository, get_workflow_repository
from backend.workflows.templates import DEMO_SCENARIO_VERSION, build_templates, get_template


logger = logging.getLogger(__name__)

CompileEvent = Callable[[RawEvent], Awaitable[CompanyBrainSkill]]
HumanOutcomeRecorder = Callable[..., Awaitable[dict[str, Any] | None]]


class WorkflowNotFoundError(LookupError):
    pass


class WorkflowTemplateNotFoundError(LookupError):
    pass


class WorkflowService:
    """Application service shared by the HTTP router and direct integrations.

    Qwen compilation is best effort.  If no key/database is available, the
    decision remains usable because the deterministic SAG trace never depends
    on a model response.  The response explicitly labels that fallback.
    """

    def __init__(
        self,
        *,
        repository: WorkflowRepository | None = None,
        compile_event: CompileEvent | None = None,
        human_outcome_recorder: HumanOutcomeRecorder | None = None,
        enable_qwen_compilation: bool | None = None,
    ) -> None:
        self._repository = repository
        self._compile_event = compile_event
        self._human_outcome_recorder = human_outcome_recorder
        self._enable_qwen_compilation = enable_qwen_compilation

    @property
    def repository(self) -> WorkflowRepository:
        return self._repository or get_workflow_repository()

    def list_templates(self) -> list[WorkflowTemplate]:
        return list(build_templates())

    def get_template(self, template_id: str) -> WorkflowTemplate:
        template = get_template(template_id)
        if template is None:
            raise WorkflowTemplateNotFoundError(template_id)
        return template

    def _should_compile(self) -> bool:
        if self._enable_qwen_compilation is not None:
            return self._enable_qwen_compilation
        return bool(settings.QWEN_API_KEY)

    @staticmethod
    def _evidence_id(
        *,
        template_id: str,
        item: EvidenceInput,
        is_fixture: bool,
        position: int,
    ) -> str:
        if is_fixture:
            identity = item.external_id or f"{item.source_type}:{position}"
            return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{DEMO_SCENARIO_VERSION}:{template_id}:{identity}"))
        return f"evidence-{uuid.uuid4().hex}"

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _normalize_evidence(
        self,
        *,
        template: WorkflowTemplate,
        items: list[EvidenceInput],
        org_id: str,
        is_fixture: bool,
        now: datetime,
    ) -> list[EvidenceRecord]:
        records: list[EvidenceRecord] = []
        for position, item in enumerate(items):
            occurred_at = self._as_utc(item.occurred_at)
            if item.availability == EvidenceAvailability.UNAVAILABLE:
                freshness = EvidenceFreshness.UNAVAILABLE
            elif occurred_at is None:
                freshness = EvidenceFreshness.UNKNOWN
            else:
                age_seconds = max(0.0, (now - occurred_at).total_seconds())
                age_hours = age_seconds / 3600
                freshness = (
                    EvidenceFreshness.STALE
                    if age_hours > template.evidence_max_age_hours
                    else EvidenceFreshness.FRESH
                )
            payload = item.model_dump()
            # Override caller-provided timestamp/freshness after normalization;
            # passing them alongside **payload would create duplicate kwargs.
            payload.update(
                {
                    "evidence_id": self._evidence_id(
                        template_id=template.template_id,
                        item=item,
                        is_fixture=is_fixture,
                        position=position,
                    ),
                    "template_id": template.template_id,
                    "scenario_version": DEMO_SCENARIO_VERSION,
                    "org_id": org_id,
                    "is_demo_fixture": is_fixture,
                    "occurred_at": occurred_at,
                    "freshness": freshness,
                    "normalized_at": now,
                }
            )
            records.append(EvidenceRecord(**payload))
        return records

    @staticmethod
    def _blank(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    def _missing_requirements(
        self,
        *,
        template: WorkflowTemplate,
        evidence: list[EvidenceRecord],
        live_context: dict[str, Any],
    ) -> list[MissingEvidence]:
        missing: list[MissingEvidence] = []
        if not evidence:
            missing.append(MissingEvidence(field="evidence", reason="No evidence records were supplied."))

        observed_types = {item.source_type for item in evidence if item.source_type}
        for source_type in template.required_source_types:
            if source_type not in observed_types:
                missing.append(
                    MissingEvidence(
                        field="source_type",
                        reason=f"Required source type '{source_type}' is absent.",
                    )
                )

        for item in evidence:
            if item.source_type not in template.source_types:
                missing.append(
                    MissingEvidence(
                        field="source_type",
                        reason=f"Unsupported source type '{item.source_type}' for this template.",
                        source_evidence_id=item.evidence_id,
                    )
                )
            for field in template.required_evidence_fields:
                if self._blank(getattr(item, field, None)):
                    missing.append(
                        MissingEvidence(
                            field=field,
                            reason="Required evidence field is missing.",
                            source_evidence_id=item.evidence_id,
                        )
                    )
            if item.availability != EvidenceAvailability.AVAILABLE:
                missing.append(
                    MissingEvidence(
                        field="availability",
                        reason=f"Evidence is {item.availability.value}; it cannot support an automated recommendation.",
                        source_evidence_id=item.evidence_id,
                    )
                )
            if item.freshness != EvidenceFreshness.FRESH:
                missing.append(
                    MissingEvidence(
                        field="freshness",
                        reason=f"Evidence freshness is {item.freshness.value}; refresh it before acting.",
                        source_evidence_id=item.evidence_id,
                    )
                )

        for field in template.live_context_schema:
            if field.required and field.name not in live_context:
                missing.append(
                    MissingEvidence(
                        field=field.name,
                        reason="Required live-context value is missing.",
                    )
                )
        return missing

    @staticmethod
    def _facts(
        evidence: list[EvidenceRecord], live_context: dict[str, Any]
    ) -> list[DecisionFact]:
        facts: list[DecisionFact] = []
        for item in evidence:
            label = item.source_name or item.source_type
            statement = item.excerpt.strip() or f"{label} supplied an evidence record."
            facts.append(DecisionFact(statement=f"{label}: {statement}", source_evidence_ids=[item.evidence_id]))
        for key, value in sorted(live_context.items()):
            facts.append(DecisionFact(statement=f"Live context — {key}: {value!r}"))
        return facts

    @staticmethod
    def _changed_condition(evidence: list[EvidenceRecord]) -> str | None:
        for item in evidence:
            metadata = item.metadata or {}
            field = metadata.get("changed_field")
            if field and "previous_value" in metadata and "current_value" in metadata:
                return (
                    f"{field} changed from {metadata['previous_value']!r} "
                    f"to {metadata['current_value']!r}."
                )
            for key, value in metadata.items():
                if key.startswith("previous_"):
                    suffix = key.removeprefix("previous_")
                    current_key = f"current_{suffix}"
                    if current_key in metadata:
                        return f"{suffix} changed from {value!r} to {metadata[current_key]!r}."
        return None

    async def _compiled_memory(
        self,
        *,
        template: WorkflowTemplate,
        evidence: list[EvidenceRecord],
        org_id: str,
        run_id: str,
        is_fixture: bool,
    ) -> tuple[MemoryReference | None, DecisionInference]:
        """Best-effort Qwen compile; never lets a compile failure change SAG."""
        fallback = DecisionInference(
            text=(
                "Qwen compilation was unavailable for this run; the recommendation is "
                "based only on cited evidence and deterministic SAG checks."
            ),
            generated_by="deterministic_sag",
            is_model_generated=False,
        )
        if not self._should_compile():
            return None, fallback

        event = RawEvent(
            event_id=f"workflow-{run_id}",
            agent_id="workflow-engine",
            event_type="workflow_evidence",
            outcome="normalized operational evidence",
            content="\n".join(
                f"[{item.source_type} {item.external_id or item.evidence_id}] {item.excerpt}"
                for item in evidence
            ),
            metadata={
                "workflow_template": template.template_id,
                "workflow_template_version": template.version,
                "source_evidence_ids": [item.evidence_id for item in evidence],
            },
            org_id=org_id,
        )
        compile_fn = self._compile_event or compiler.compile_event_to_skill
        try:
            skill = await compile_fn(event)
            persisted = False
            skill_id: str | None = None
            # Fixture compilation is intentionally ephemeral: it must never add
            # skills, confidence, or duplicate canonical judge-demo records.
            if not is_fixture:
                try:
                    saved = await brain_store.save_skill(skill, org_id=org_id)
                    skill_id = saved.skill_id
                    persisted = True
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Workflow compiled memory could not be persisted: %s", exc)
            return (
                MemoryReference(
                    memory_id=f"compiled:{skill.skill_id}:{run_id}",
                    memory_type=template.memory_type,
                    summary=skill.summary or skill.name,
                    skill_id=skill_id,
                    is_ephemeral=is_fixture or not persisted,
                    provenance={
                        "compiler": "qwen",
                        "source_event_id": event.event_id,
                        "source_evidence_ids": [item.evidence_id for item in evidence],
                        "persisted": persisted,
                        "kind": "compiled_event",
                    },
                ),
                DecisionInference(
                    text=(
                        "Qwen compiled the cited evidence into a memory candidate: "
                        f"{skill.summary or skill.name}"
                    ),
                    generated_by="qwen_compiler",
                    is_model_generated=True,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Workflow Qwen compilation failed; retaining deterministic decision: %s", exc)
            return None, fallback

    async def _existing_compiled_memory(
        self,
        *,
        skill_id: str,
        template: WorkflowTemplate,
        evidence: list[EvidenceRecord],
        org_id: str,
    ) -> tuple[MemoryReference | None, DecisionInference]:
        """Attach a durable source-event skill without compiling it a second time."""
        fallback = DecisionInference(
            text=(
                "The supplied compiled-memory reference could not be verified; the "
                "recommendation is based only on cited evidence and deterministic SAG checks."
            ),
            generated_by="deterministic_sag",
            is_model_generated=False,
        )
        try:
            skill = await brain_store.get_skill(skill_id, org_id=org_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Workflow compiled-memory lookup failed: %s", exc)
            return None, fallback
        if skill is None:
            logger.warning("Workflow compiled-memory reference not found: %s", skill_id)
            return None, fallback
        return (
            MemoryReference(
                memory_id=f"compiled:{skill.skill_id}",
                memory_type=template.memory_type,
                summary=skill.summary or skill.name,
                skill_id=skill.skill_id,
                is_ephemeral=False,
                provenance={
                    "compiler": "qwen",
                    "source_evidence_ids": [item.evidence_id for item in evidence],
                    "persisted": True,
                    "kind": "compiled_event",
                    "reused_from_source_event": True,
                },
            ),
            DecisionInference(
                text=(
                    "Qwen previously compiled the cited source event into an "
                    f"organizational memory: {skill.summary or skill.name}"
                ),
                generated_by="qwen_compiler",
                is_model_generated=True,
            ),
        )

    async def run_workflow(
        self,
        body: WorkflowRunRequest,
        *,
        org_id: str,
        persist: bool = True,
        compile_memory: bool = True,
    ) -> WorkflowRun:
        template = self.get_template(body.template_id)
        now = workflow_now()
        is_fixture = body.fixture
        input_evidence = body.evidence or (template.demo_fixture.evidence if is_fixture else [])
        live_context = dict(body.live_context or (template.demo_fixture.live_context if is_fixture else {}))
        evidence = self._normalize_evidence(
            template=template,
            items=input_evidence,
            org_id=org_id,
            is_fixture=is_fixture,
            now=now,
        )
        run_id = f"workflow-{uuid.uuid4().hex}"
        missing = self._missing_requirements(
            template=template,
            evidence=evidence,
            live_context=live_context,
        )

        sag_trace: dict[str, Any]
        if missing:
            verdict = WorkflowVerdict.REVIEW_REQUIRED
            status = WorkflowRunStatus.REVIEW_REQUIRED
            sag_trace = {
                "status": "not_evaluated",
                "reason": "Required evidence or live context is missing, stale, unavailable, or unsupported.",
                "rule": template.sag_rule,
                "trace": None,
                "evaluated_in_ms": 0.0,
            }
        else:
            try:
                sag = evaluate_rule(template.sag_rule, live_context)
            except SagRuleError as exc:
                logger.exception("Invalid code-owned workflow SAG rule: %s", exc)
                raise RuntimeError(f"Workflow template SAG rule is invalid: {exc.code}") from exc
            active = bool(sag["result"])
            verdict = (
                WorkflowVerdict.PROCEED_WITH_HUMAN_APPROVAL
                if active
                else WorkflowVerdict.SUSPENDED
            )
            status = (
                WorkflowRunStatus.AWAITING_HUMAN_APPROVAL
                if active
                else WorkflowRunStatus.SUSPENDED
            )
            sag_trace = {
                "status": "evaluated",
                "rule": template.sag_rule,
                "result": active,
                "trace": sag["trace"],
                "evaluated_in_ms": sag["evaluated_in_ms"],
            }

        template_memory = MemoryReference(
            memory_id=f"template:{template.template_id}:v{template.version}",
            memory_type=template.memory_type,
            summary=template.prior_memory_summary,
            is_ephemeral=False,
            provenance={
                "template_id": template.template_id,
                "template_version": template.version,
                "scenario_version": DEMO_SCENARIO_VERSION,
                "kind": "prior_memory",
            },
        )
        if body.compiled_skill_id and not is_fixture:
            compiled_memory, inference = await self._existing_compiled_memory(
                skill_id=body.compiled_skill_id,
                template=template,
                evidence=evidence,
                org_id=org_id,
            )
        elif compile_memory:
            compiled_memory, inference = await self._compiled_memory(
                template=template,
                evidence=evidence,
                org_id=org_id,
                run_id=run_id,
                is_fixture=is_fixture,
            )
        else:
            compiled_memory = None
            inference = DecisionInference(
                text=(
                    "This server-owned fixture preview is deterministic. Run the fixture "
                    "to compile its cited evidence with Qwen without changing canonical memory."
                ),
                generated_by="deterministic_sag",
                is_model_generated=False,
            )
        changed = self._changed_condition(evidence)
        if changed:
            inference.text = f"{inference.text} Observed change: {changed}"
        if verdict == WorkflowVerdict.SUSPENDED:
            inference.text = f"{inference.text} The live context no longer satisfies the prior memory."
        elif verdict == WorkflowVerdict.REVIEW_REQUIRED:
            inference.text = f"{inference.text} No action is recommended until the missing evidence is supplied."
        else:
            inference.text = f"{inference.text} The path remains eligible only for a human-approved action."

        memory_refs = [template_memory]
        if compiled_memory:
            memory_refs.append(compiled_memory)
        brief = DecisionBrief(
            facts=self._facts(evidence, live_context),
            inference=inference,
            missing_evidence=missing,
            evidence=evidence,
            memory_refs=memory_refs,
            sag_trace=sag_trace,
            verdict=verdict,
            status=status,
            owner=template.owner_role,
            recommended_next_action=template.recommended_action,
            human_approval_required=template.human_approval_required,
        )
        run = WorkflowRun(
            run_id=run_id,
            template_id=template.template_id,
            template_version=template.version,
            scenario_version=DEMO_SCENARIO_VERSION,
            org_id=org_id,
            is_demo_fixture=is_fixture,
            live_context=live_context,
            decision_brief=brief,
            created_at=now,
            updated_at=now,
        )
        # Non-fixture inputs become a source catalog.  Canonical fixtures are
        # regenerated read-only from code so demo clicks cannot pollute it.
        if not is_fixture and persist:
            await self.repository.save_sources(evidence)
        return await self.repository.save_run(run) if persist else run

    async def preview_fixture(self, template_id: str) -> WorkflowRun:
        """Return a server-evaluated fixture preview without a database write.

        This powers the default judge inbox. It intentionally skips Qwen calls
        so a harmless GET cannot incur model cost or manufacture durable memory;
        an explicit POST fixture run exercises the compiler ephemerally.
        """
        return await self.run_workflow(
            WorkflowRunRequest(template_id=template_id, fixture=True),
            org_id=settings.JUDGE_DEMO_ORG_ID,
            persist=False,
            compile_memory=False,
        )

    async def get_run(self, run_id: str, *, org_id: str) -> WorkflowRun:
        run = await self.repository.get_run(run_id, org_id)
        if run is None:
            raise WorkflowNotFoundError(run_id)
        return run

    def _compiled_skill_id(self, run: WorkflowRun) -> str | None:
        for memory in run.decision_brief.memory_refs:
            if memory.skill_id and memory.provenance.get("kind") == "compiled_event":
                return memory.skill_id
        return None

    async def record_outcome(
        self,
        run_id: str,
        body: WorkflowOutcomeRequest,
        *,
        org_id: str,
    ) -> WorkflowRun:
        run = await self.get_run(run_id, org_id=org_id)
        reinforced = False
        system_note: str | None = None
        skill_id = self._compiled_skill_id(run)
        can_reinforce = (
            not run.is_demo_fixture
            and body.approved
            and body.outcome == "confirmed_effective"
            and bool(body.actor)
            and bool(skill_id)
        )
        if can_reinforce and skill_id:
            recorder = self._human_outcome_recorder or getattr(brain_store, "record_human_outcome", None)
            if recorder is None:
                system_note = "Human outcome recorded locally; skill reinforcement service is unavailable."
            else:
                try:
                    result = await recorder(
                        skill_id,
                        org_id,
                        body.outcome,
                        body.actor,
                        note=body.note,
                        source_run_id=run.run_id,
                    )
                    reinforced = bool((result or {}).get("reinforced"))
                    if not reinforced:
                        system_note = "Human outcome recorded; compiled memory was not reinforced."
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Human outcome recorder failed for workflow %s: %s", run_id, exc)
                    system_note = "Human outcome recorded locally; reinforcement could not be completed."
        elif body.approved and body.outcome == "confirmed_effective":
            system_note = (
                "No reinforcement: fixture runs, missing actor, or unpersisted memory "
                "cannot change confidence."
            )

        outcome = WorkflowOutcome(
            approved=body.approved,
            outcome=body.outcome,
            actor=body.actor,
            reinforcement_eligible=can_reinforce,
            reinforcement_applied=reinforced,
            note=body.note.strip() or system_note,
        )
        run.outcomes.append(outcome)
        if body.approved:
            next_status = WorkflowRunStatus.RESOLVED
        elif body.outcome == "needs_review":
            next_status = WorkflowRunStatus.REVIEW_REQUIRED
        else:
            next_status = WorkflowRunStatus.REJECTED
        run.decision_brief.status = next_status
        run.updated_at = workflow_now()
        return await self.repository.save_run(run)

    async def list_sources(
        self,
        *,
        org_id: str,
        template_id: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        """Expose immutable canonical sources plus org-scoped persisted inputs."""
        max_items = max(1, min(limit, 200))
        canonical: list[EvidenceRecord] = []
        now = workflow_now()
        for template in self.list_templates():
            if template_id and template.template_id != template_id:
                continue
            canonical.extend(
                self._normalize_evidence(
                    template=template,
                    items=template.demo_fixture.evidence,
                    org_id=org_id,
                    is_fixture=True,
                    now=now,
                )
            )
        persisted = await self.repository.list_sources(
            org_id=org_id,
            template_id=template_id,
            limit=max_items,
        )
        merged: dict[str, EvidenceRecord] = {item.evidence_id: item for item in canonical}
        for item in persisted:
            merged[item.evidence_id] = item
        values = list(merged.values())
        values.sort(key=lambda item: item.occurred_at or item.normalized_at, reverse=True)
        return values[:max_items]
