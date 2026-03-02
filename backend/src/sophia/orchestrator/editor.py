"""Editor Agent: daily ReAct cycle orchestrator.

Runs the full autonomous loop per client: observe, research, generate,
judge, approve/flag, learn. Each stage is wrapped in a timeout with
structured audit logging via CycleStage records.

Stage failures do NOT abort the cycle -- the cycle continues to subsequent
stages, and the CycleRun is marked "partial" if any stage failed.

This is the core of Phase 7: the module that transforms Sophia from a
set of tools into an autonomous agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Per-stage timeout constants (seconds)
STAGE_TIMEOUTS = {
    "observe": 30,
    "research": 120,  # 2 min -- MCP calls can be slow
    "generate": 120,  # 2 min -- content generation
    "judge": 30,  # quick evaluation
    "approve": 15,  # state transition
    "learn": 30,  # learning extraction
}


# ---------------------------------------------------------------------------
# Stage runner helper
# ---------------------------------------------------------------------------


async def _run_stage(
    db: Session,
    cycle_run_id: int,
    stage_name: str,
    func: Callable[..., Any],
    timeout: float,
    **kwargs: Any,
) -> Optional[Any]:
    """Execute a single cycle stage with timeout, audit logging, and error handling.

    Creates a CycleStage record, runs the function with asyncio.wait_for timeout,
    and updates the stage record with result or error.

    Stage failures do NOT abort the cycle -- returns None on failure so the
    caller can continue to subsequent stages.
    """
    from sophia.orchestrator.models import CycleStage

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stage = CycleStage(
        cycle_run_id=cycle_run_id,
        stage_name=stage_name,
        status="running",
        started_at=now,
    )
    db.add(stage)
    db.flush()

    try:
        result = await asyncio.wait_for(func(**kwargs), timeout=timeout)

        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_ms = int((completed_at - now).total_seconds() * 1000)
        stage.status = "completed"
        stage.completed_at = completed_at
        stage.duration_ms = duration_ms

        # Store decision trace if result is serializable
        if result is not None:
            try:
                if hasattr(result, "__dict__"):
                    trace = {
                        k: v
                        for k, v in result.__dict__.items()
                        if not k.startswith("_")
                    }
                    # Convert non-serializable values
                    for k, v in trace.items():
                        if isinstance(v, datetime):
                            trace[k] = v.isoformat()
                    stage.decision_trace = trace
                elif isinstance(result, dict):
                    stage.decision_trace = result
                elif isinstance(result, list):
                    stage.decision_trace = {"items": len(result)}
            except Exception:
                stage.decision_trace = {"result": str(result)[:500]}

        db.flush()
        return result

    except asyncio.TimeoutError:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_ms = int((completed_at - now).total_seconds() * 1000)
        stage.status = "failed"
        stage.completed_at = completed_at
        stage.duration_ms = duration_ms
        stage.error_message = f"Timeout after {timeout}s"
        db.flush()
        logger.warning(
            "Stage %s timed out after %ss for cycle %d",
            stage_name,
            timeout,
            cycle_run_id,
        )
        return None

    except Exception as exc:
        completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_ms = int((completed_at - now).total_seconds() * 1000)
        stage.status = "failed"
        stage.completed_at = completed_at
        stage.duration_ms = duration_ms
        stage.error_message = str(exc)[:1000]
        db.flush()
        logger.exception(
            "Stage %s failed for cycle %d: %s",
            stage_name,
            cycle_run_id,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Daily cycle orchestrator
# ---------------------------------------------------------------------------


async def run_daily_cycle(
    db: Session,
    client_id: int,
) -> "CycleRun":
    """Run the full daily ReAct cycle for a single client.

    Stages: observe -> research (conditional) -> generate -> judge+approve -> learn

    Each stage is wrapped in _run_stage with per-stage timeouts.
    Stage failures do NOT abort the cycle -- subsequent stages still execute.

    Returns:
        CycleRun with status "completed" (all OK), "partial" (some stages failed),
        or "failed" (setup itself failed).
    """
    from sophia.orchestrator.models import CycleRun

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    has_failure = False
    drafts = []
    auto_approved_count = 0
    flagged_count = 0
    research_count = 0
    observation = None

    # Setup: create CycleRun and get specialist
    cycle = CycleRun(
        client_id=client_id,
        status="running",
        started_at=now,
    )
    db.add(cycle)
    db.flush()

    try:
        from sophia.orchestrator.specialist import get_or_create_specialist

        specialist = get_or_create_specialist(db, client_id)
        cycle.specialist_agent_id = specialist.id
        db.flush()
    except Exception as exc:
        logger.exception("Failed to get/create specialist for client %d", client_id)
        cycle.status = "failed"
        cycle.error_message = f"Setup failed: {exc}"
        cycle.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.flush()
        return cycle

    # STAGE 1: OBSERVE
    async def _observe(db=db, client_id=client_id):
        from sophia.orchestrator.observer import observe_client_state

        return await asyncio.to_thread(observe_client_state, db, client_id)

    observation = await _run_stage(
        db, cycle.id, "observe", _observe, STAGE_TIMEOUTS["observe"]
    )
    if observation is None:
        has_failure = True

    # STAGE 2: RESEARCH (conditional)
    needs_research = observation.needs_research if observation else True

    if needs_research:

        async def _research(db=db, client_id=client_id):
            from sophia.research.service import run_research_cycle

            return await run_research_cycle(db, client_id)

        research_result = await _run_stage(
            db, cycle.id, "research", _research, STAGE_TIMEOUTS["research"]
        )
        if research_result is None:
            has_failure = True
        else:
            research_count = getattr(
                research_result, "total_findings", 0
            ) or (
                research_result.get("findings_count", 0)
                if isinstance(research_result, dict)
                else 0
            )
    else:
        # Log skipped research stage
        from sophia.orchestrator.models import CycleStage

        skip_now = datetime.now(timezone.utc).replace(tzinfo=None)
        skip_stage = CycleStage(
            cycle_run_id=cycle.id,
            stage_name="research",
            status="skipped",
            started_at=skip_now,
            completed_at=skip_now,
            duration_ms=0,
            decision_trace={"reason": "Research not needed (fresh findings exist)"},
        )
        db.add(skip_stage)
        db.flush()

    # STAGE 3: GENERATE
    async def _generate(db=db, client_id=client_id):
        from sophia.content.service import generate_content_batch

        return await asyncio.to_thread(generate_content_batch, db, client_id)

    generated = await _run_stage(
        db, cycle.id, "generate", _generate, STAGE_TIMEOUTS["generate"]
    )
    if generated is None:
        has_failure = True
    else:
        drafts = generated if isinstance(generated, list) else []
        # Set cycle_id on each draft
        for d in drafts:
            d.cycle_id = cycle.id
        db.flush()

    # STAGE 4: JUDGE + APPROVE (per draft)
    if drafts:
        judgments = []

        async def _judge_and_approve(
            db=db, drafts=drafts, observation=observation, cycle_id=cycle.id
        ):
            from sophia.orchestrator.auto_approval import should_auto_approve

            results = {"judgments": [], "auto_approved": 0, "flagged": 0}

            for draft in drafts:
                obs = observation if observation else _default_observation(
                    client_id
                )
                judgment = should_auto_approve(db, draft, obs)
                judgment_dict = {
                    "draft_id": judgment.draft_id,
                    "auto_approve": judgment.auto_approve,
                    "rationale": judgment.rationale,
                    "confidence_score": judgment.confidence_score,
                }
                results["judgments"].append(judgment_dict)

                if judgment.auto_approve:
                    try:
                        from sophia.approval.service import approve_draft

                        approve_draft(
                            db,
                            draft.id,
                            publish_mode="auto",
                            actor="sophia:editor",
                        )
                        results["auto_approved"] += 1
                    except Exception as exc:
                        logger.warning(
                            "Auto-approval failed for draft %d: %s",
                            draft.id,
                            exc,
                        )
                        results["flagged"] += 1
                else:
                    results["flagged"] += 1

            return results

        judge_result = await _run_stage(
            db, cycle.id, "judge", _judge_and_approve, STAGE_TIMEOUTS["judge"]
        )
        if judge_result is None:
            has_failure = True
            flagged_count = len(drafts)
        else:
            auto_approved_count = judge_result.get("auto_approved", 0)
            flagged_count = judge_result.get("flagged", 0)
    else:
        # No drafts to judge -- log skipped stage
        from sophia.orchestrator.models import CycleStage as CS

        skip_now = datetime.now(timezone.utc).replace(tzinfo=None)
        skip_stage = CS(
            cycle_run_id=cycle.id,
            stage_name="judge",
            status="skipped",
            started_at=skip_now,
            completed_at=skip_now,
            duration_ms=0,
            decision_trace={"reason": "No drafts generated to judge"},
        )
        db.add(skip_stage)
        db.flush()

    # STAGE 5: LEARN
    async def _learn(
        db=db,
        client_id=client_id,
        cycle_id=cycle.id,
        specialist=specialist,
        auto_approved=auto_approved_count,
        flagged=flagged_count,
        drafts_count=len(drafts),
    ):
        from sophia.agent.learning import persist_learning
        from sophia.orchestrator.specialist import update_specialist_state

        # Persist cycle outcome learning
        learning_content = (
            f"Cycle completed: {drafts_count} drafts generated, "
            f"{auto_approved} auto-approved, {flagged} flagged for review"
        )
        learning = persist_learning(
            db,
            client_id,
            learning_type="content",
            source="cycle_outcome",
            content=learning_content,
            cycle_run_id=cycle_id,
        )

        # Update specialist state with cycle results
        new_state = {
            "recent_cycles": [
                {
                    "cycle_id": cycle_id,
                    "drafts": drafts_count,
                    "auto_approved": auto_approved,
                    "flagged": flagged,
                    "timestamp": datetime.now(timezone.utc)
                    .replace(tzinfo=None)
                    .isoformat(),
                }
            ]
        }
        update_specialist_state(db, specialist.id, new_state, cycle_id)

        return {"learning_id": learning.id, "specialist_updated": True}

    learn_result = await _run_stage(
        db, cycle.id, "learn", _learn, STAGE_TIMEOUTS["learn"]
    )
    if learn_result is None:
        has_failure = True

    # Finalize CycleRun
    cycle.status = "partial" if has_failure else "completed"
    cycle.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    cycle.drafts_generated = len(drafts)
    cycle.drafts_auto_approved = auto_approved_count
    cycle.drafts_flagged = flagged_count
    cycle.research_findings_count = research_count
    cycle.learnings_extracted = 1 if learn_result else 0

    if observation is not None:
        try:
            obs_dict = {
                k: v
                for k, v in observation.__dict__.items()
                if not k.startswith("_")
            }
            for k, v in obs_dict.items():
                if isinstance(v, datetime):
                    obs_dict[k] = v.isoformat()
            cycle.observation_summary = obs_dict
        except Exception:
            pass

    db.flush()
    logger.info(
        "Cycle %d for client %d: status=%s drafts=%d auto_approved=%d flagged=%d",
        cycle.id,
        client_id,
        cycle.status,
        len(drafts),
        auto_approved_count,
        flagged_count,
    )

    return cycle


def _default_observation(client_id: int):
    """Create a minimal observation when the observe stage failed."""
    from sophia.orchestrator.observer import ClientObservation

    return ClientObservation(
        client_id=client_id,
        client_name="Unknown",
        last_post_date=None,
        days_since_last_post=9999,
        pending_approvals=0,
        recent_engagement_trend="stable",
        research_freshness_hours=None,
        needs_research=True,
        active_anomalies=0,
        approval_rate_30d=0.0,
        completed_cycles=0,
    )


# ---------------------------------------------------------------------------
# All-client cycle runner
# ---------------------------------------------------------------------------


async def run_all_client_cycles(
    session_factory: Callable,
) -> list[dict]:
    """Run daily cycles for all active (non-archived) clients sequentially.

    Per CONTEXT.md locked decision: cron-style, not event-driven.
    Clients are processed sequentially to avoid resource contention.

    After all cycles, generates an exception briefing for operator review.

    Returns:
        List of per-client result dicts.
    """
    db = session_factory()
    try:
        from sophia.intelligence.models import Client

        clients = (
            db.query(Client)
            .filter(Client.is_archived.is_(False))
            .order_by(Client.id)
            .all()
        )
    finally:
        db.close()

    results = []
    for client in clients:
        db = session_factory()
        try:
            cycle = await run_daily_cycle(db, client.id)
            results.append(
                {
                    "client_id": client.id,
                    "client_name": client.name,
                    "cycle_id": cycle.id,
                    "status": cycle.status,
                    "auto_approved": cycle.drafts_auto_approved,
                    "flagged": cycle.drafts_flagged,
                    "drafts_generated": cycle.drafts_generated,
                }
            )
            db.commit()
        except Exception as exc:
            logger.exception(
                "Cycle failed entirely for client %d: %s", client.id, exc
            )
            results.append(
                {
                    "client_id": client.id,
                    "client_name": client.name,
                    "cycle_id": None,
                    "status": "failed",
                    "auto_approved": 0,
                    "flagged": 0,
                    "drafts_generated": 0,
                    "error": str(exc)[:500],
                }
            )
            db.rollback()
        finally:
            db.close()

    # Generate exception briefing
    db = session_factory()
    try:
        briefing = await generate_exception_briefing(db, results)
        db.commit()
    except Exception:
        logger.exception("Failed to generate exception briefing")
        db.rollback()
    finally:
        db.close()

    return results


# ---------------------------------------------------------------------------
# Exception briefing
# ---------------------------------------------------------------------------


async def generate_exception_briefing(
    db: Session,
    cycle_results: list[dict],
) -> dict:
    """Generate an exception briefing aggregating all client cycle results.

    Summarizes auto-approved count, flagged count, failures, and lists
    flagged drafts with rationale for operator daily review.

    Persisted as a Briefing record (briefing_type="exception_briefing").
    """
    from sophia.agent.models import Briefing

    total_auto_approved = sum(r.get("auto_approved", 0) for r in cycle_results)
    total_flagged = sum(r.get("flagged", 0) for r in cycle_results)
    total_failures = sum(1 for r in cycle_results if r.get("status") == "failed")
    total_drafts = sum(r.get("drafts_generated", 0) for r in cycle_results)

    # Collect failed cycles
    failed_cycles = [
        {
            "client_id": r["client_id"],
            "client_name": r.get("client_name", "Unknown"),
            "error": r.get("error", "Unknown error"),
        }
        for r in cycle_results
        if r.get("status") == "failed"
    ]

    # Collect partial cycles
    partial_cycles = [
        {
            "client_id": r["client_id"],
            "client_name": r.get("client_name", "Unknown"),
            "auto_approved": r.get("auto_approved", 0),
            "flagged": r.get("flagged", 0),
        }
        for r in cycle_results
        if r.get("status") == "partial"
    ]

    briefing_data = {
        "type": "exception_briefing",
        "summary": {
            "total_clients": len(cycle_results),
            "total_drafts_generated": total_drafts,
            "total_auto_approved": total_auto_approved,
            "total_flagged": total_flagged,
            "total_failures": total_failures,
        },
        "failed_cycles": failed_cycles,
        "partial_cycles": partial_cycles,
        "client_results": cycle_results,
    }

    # Persist as Briefing
    briefing_record = Briefing(
        briefing_type="exception_briefing",
        content_json=json.dumps(briefing_data),
    )
    db.add(briefing_record)
    db.flush()

    logger.info(
        "Exception briefing: %d clients, %d auto-approved, %d flagged, %d failures",
        len(cycle_results),
        total_auto_approved,
        total_flagged,
        total_failures,
    )

    return briefing_data
