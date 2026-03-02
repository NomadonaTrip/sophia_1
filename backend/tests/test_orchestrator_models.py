"""Integration tests for orchestrator models and specialist service.

Tests CycleRun, CycleStage, SpecialistAgent, ChatMessage,
AutoApprovalConfig models, and the specialist CRUD service
with state compaction and false positive tracking.
"""

from datetime import datetime, timedelta

from sophia.content.models import ContentDraft
from sophia.orchestrator.models import (
    AutoApprovalConfig,
    ChatMessage,
    CycleRun,
    CycleStage,
    SpecialistAgent,
)
from sophia.orchestrator.specialist import (
    compact_state,
    create_specialist,
    deactivate_specialist,
    get_or_create_specialist,
    record_false_positive,
    update_approval_rate,
    update_specialist_state,
)


class TestCycleRun:
    """Tests for CycleRun model creation and defaults."""

    def test_create_cycle_run(self, db_session, sample_client):
        """Create CycleRun linked to sample_client, verify defaults."""
        run = CycleRun(client_id=sample_client.id)
        db_session.add(run)
        db_session.flush()

        assert run.id is not None
        assert run.client_id == sample_client.id
        assert run.status == "pending"
        assert run.drafts_generated == 0
        assert run.drafts_auto_approved == 0
        assert run.drafts_flagged == 0
        assert run.research_findings_count == 0
        assert run.learnings_extracted == 0
        assert run.started_at is None
        assert run.completed_at is None
        assert run.observation_summary is None
        assert run.judgment_summary is None

    def test_cycle_run_with_stages(self, db_session, sample_client):
        """Create CycleRun with 3 CycleStages, verify FK linkage and JSON."""
        run = CycleRun(client_id=sample_client.id, status="running")
        db_session.add(run)
        db_session.flush()

        stage_names = ["observe", "research", "generate"]
        stages = []
        for name in stage_names:
            stage = CycleStage(
                cycle_run_id=run.id,
                stage_name=name,
                status="completed",
                duration_ms=1500,
                decision_trace={"action": f"ran_{name}", "confidence": 0.9},
            )
            db_session.add(stage)
            stages.append(stage)

        db_session.flush()

        # Verify FK linkage
        for stage in stages:
            assert stage.cycle_run_id == run.id
            assert stage.id is not None

        # Verify decision_trace JSON storage
        loaded = (
            db_session.query(CycleStage)
            .filter(CycleStage.cycle_run_id == run.id)
            .all()
        )
        assert len(loaded) == 3
        assert loaded[0].decision_trace["action"] == "ran_observe"
        assert loaded[0].decision_trace["confidence"] == 0.9


class TestSpecialistService:
    """Tests for specialist agent CRUD and state management."""

    def test_specialist_create_and_load(self, db_session, sample_client):
        """create_specialist returns agent with empty state and zero cycles."""
        agent = create_specialist(db_session, sample_client.id)

        assert agent.id is not None
        assert agent.client_id == sample_client.id
        assert agent.specialty == "general"
        assert agent.state_json == {}
        assert agent.total_cycles == 0
        assert agent.is_active is True

    def test_specialist_get_or_create_idempotent(
        self, db_session, sample_client
    ):
        """get_or_create_specialist called twice returns same record."""
        first = get_or_create_specialist(db_session, sample_client.id)
        second = get_or_create_specialist(db_session, sample_client.id)

        assert first.id == second.id

    def test_specialist_state_update(self, db_session, sample_client):
        """update_specialist_state merges and caps list fields at 50."""
        agent = create_specialist(db_session, sample_client.id)

        # Create a cycle run for tracking
        run = CycleRun(client_id=sample_client.id)
        db_session.add(run)
        db_session.flush()

        # First update: add 30 learnings
        learnings_batch_1 = [f"learning_{i}" for i in range(30)]
        update_specialist_state(
            db_session,
            agent.id,
            {"learnings": learnings_batch_1},
            run.id,
        )
        assert len(agent.state_json["learnings"]) == 30
        assert agent.total_cycles == 1
        assert agent.last_cycle_id == run.id

        # Second update: add 30 more (total 60, should be capped to 50)
        run2 = CycleRun(client_id=sample_client.id)
        db_session.add(run2)
        db_session.flush()

        learnings_batch_2 = [f"learning_{i}" for i in range(30, 60)]
        update_specialist_state(
            db_session,
            agent.id,
            {"learnings": learnings_batch_2},
            run2.id,
        )
        assert len(agent.state_json["learnings"]) == 50
        assert agent.total_cycles == 2
        # Verify last 50 are kept (indices 10-59)
        assert agent.state_json["learnings"][0] == "learning_10"
        assert agent.state_json["learnings"][-1] == "learning_59"

    def test_compact_state(self):
        """compact_state prunes list values to max_entries."""
        state = {
            "learnings": list(range(100)),
            "topics": list(range(60)),
            "config": {"key": "value"},  # non-list preserved
            "short_list": [1, 2, 3],  # under limit preserved
        }
        result = compact_state(state, max_entries=50)

        assert len(result["learnings"]) == 50
        assert result["learnings"][0] == 50  # last 50 of 0-99
        assert len(result["topics"]) == 50
        assert result["topics"][0] == 10  # last 50 of 0-59
        assert result["config"] == {"key": "value"}
        assert result["short_list"] == [1, 2, 3]

        # Verify original not mutated
        assert len(state["learnings"]) == 100


class TestAutoApprovalConfig:
    """Tests for auto-approval configuration and false positive tracking."""

    def test_auto_approval_config_defaults(self, db_session, sample_client):
        """AutoApprovalConfig defaults: disabled, burn_in=15."""
        config = AutoApprovalConfig(client_id=sample_client.id)
        db_session.add(config)
        db_session.flush()

        assert config.id is not None
        assert config.enabled is False
        assert config.burn_in_cycles == 15
        assert config.completed_cycles == 0
        assert config.min_voice_confidence == 0.75
        assert config.require_all_gates_pass is True
        assert config.max_content_risk == "safe"
        assert config.min_historical_approval_rate == 0.80
        assert config.editor_override_enabled is True

    def test_false_positive_tracking(self, db_session, sample_client):
        """3 false positives within 7 days auto-disables auto-approval."""
        agent = create_specialist(db_session, sample_client.id)

        # Create and enable auto-approval config
        config = AutoApprovalConfig(client_id=sample_client.id, enabled=True)
        db_session.add(config)
        db_session.flush()

        assert config.enabled is True

        # Record 3 false positives
        record_false_positive(db_session, agent.id)
        record_false_positive(db_session, agent.id)
        record_false_positive(db_session, agent.id)

        assert agent.false_positive_count == 3
        assert agent.false_positive_window_start is not None

        # Verify auto-approval was disabled
        db_session.refresh(config)
        assert config.enabled is False


class TestChatMessage:
    """Tests for ChatMessage persistence."""

    def test_chat_message_persistence(self, db_session, sample_client):
        """Create ChatMessage, verify role, content, client_context_id."""
        msg = ChatMessage(
            role="user",
            content="Let's talk about Orban Forest",
            client_context_id=sample_client.id,
            intent_type="context_switch",
            metadata_json={"resolved_client": "Orban Forest"},
        )
        db_session.add(msg)
        db_session.flush()

        loaded = db_session.get(ChatMessage, msg.id)
        assert loaded is not None
        assert loaded.role == "user"
        assert loaded.content == "Let's talk about Orban Forest"
        assert loaded.client_context_id == sample_client.id
        assert loaded.intent_type == "context_switch"
        assert loaded.metadata_json["resolved_client"] == "Orban Forest"


class TestContentDraftCycleFk:
    """Tests for ContentDraft.cycle_id FK to CycleRun."""

    def test_content_draft_cycle_fk(self, db_session, sample_client):
        """Create CycleRun then ContentDraft with cycle_id, verify linkage."""
        run = CycleRun(client_id=sample_client.id, status="completed")
        db_session.add(run)
        db_session.flush()

        draft = ContentDraft(
            client_id=sample_client.id,
            cycle_id=run.id,
            platform="facebook",
            content_type="feed",
            copy="Test content for cycle FK verification",
            image_prompt="A scenic landscape",
            image_ratio="1:1",
        )
        db_session.add(draft)
        db_session.flush()

        assert draft.cycle_id == run.id

        # Verify via query
        loaded = db_session.get(ContentDraft, draft.id)
        assert loaded.cycle_id == run.id
