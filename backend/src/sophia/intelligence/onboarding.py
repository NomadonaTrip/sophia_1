"""Onboarding state machine with multi-session resume and skip-and-flag.

Tracks per-client progress through onboarding field groups.
State persists in Client.onboarding_state (JSON column).
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from sophia.intelligence.models import Client


# Ordered field groups for onboarding
ONBOARDING_FIELDS: list[dict] = [
    {
        "group": "business_basics",
        "label": "Business Basics",
        "fields": ["name", "industry", "business_description"],
        "why": "These fundamentals shape every piece of content Sophia creates.",
    },
    {
        "group": "geography",
        "label": "Geography",
        "fields": ["geography_area", "geography_radius_km"],
        "why": "Location scoping ensures content resonates with the local market.",
    },
    {
        "group": "market_scope",
        "label": "Market Scope",
        "fields": ["industry_vertical", "competitors"],
        "why": "Understanding the competitive landscape helps differentiate content.",
    },
    {
        "group": "content_strategy",
        "label": "Content Strategy",
        "fields": ["content_pillars", "posting_cadence"],
        "why": "Content pillars define what topics to cover; cadence sets the rhythm.",
    },
    {
        "group": "audience",
        "label": "Target Audience",
        "fields": ["target_audience"],
        "why": "Knowing who the content is for makes every post more effective.",
    },
    {
        "group": "guardrails",
        "label": "Content Guardrails",
        "fields": ["guardrails"],
        "why": "Guardrails prevent content that could harm the brand.",
    },
    {
        "group": "brand",
        "label": "Brand Assets",
        "fields": ["brand_assets"],
        "why": "Brand visuals and style guide image prompts and content tone.",
    },
    {
        "group": "platforms",
        "label": "Platform Accounts",
        "fields": ["platform_accounts"],
        "why": "Connecting platforms enables automated publishing and analytics.",
    },
    {
        "group": "voice",
        "label": "Voice Profile",
        "fields": [],  # Handled by VoiceService, tracked here for completeness
        "why": "The voice profile ensures all content sounds authentically like the client.",
    },
]

FIELD_GROUP_NAMES = [f["group"] for f in ONBOARDING_FIELDS]


class OnboardingService:
    """Onboarding state machine with multi-session resume and skip-and-flag."""

    @staticmethod
    def initialize_onboarding(client: Client) -> dict:
        """Create initial onboarding state.

        business_basics starts as completed (name + industry set at creation).
        All other field groups start as pending.
        """
        now = datetime.now(timezone.utc).isoformat()
        return {
            "phase": "business_basics",
            "completed_fields": ["business_basics"],
            "pending_fields": [
                g for g in FIELD_GROUP_NAMES if g != "business_basics"
            ],
            "skipped_fields": [],
            "started_at": now,
            "last_interaction": now,
            "session_count": 1,
            "notes": None,
        }

    @staticmethod
    def get_onboarding_status(client: Client) -> dict:
        """Return current onboarding state with computed fields.

        Returns: phase, completed_fields, pending_fields, skipped_fields,
                 percent_complete, next_field_group.
        """
        state = client.onboarding_state or {}
        completed = state.get("completed_fields", [])
        pending = state.get("pending_fields", [])
        skipped = state.get("skipped_fields", [])

        total = len(FIELD_GROUP_NAMES)
        done_count = len(completed)
        percent = int((done_count / total) * 100) if total > 0 else 0

        # Next field group is the first pending one
        next_group = pending[0] if pending else None

        return {
            "phase": state.get("phase", "unknown"),
            "completed_fields": completed,
            "pending_fields": pending,
            "skipped_fields": skipped,
            "percent_complete": percent,
            "next_field_group": next_group,
            "session_count": state.get("session_count", 0),
            "started_at": state.get("started_at"),
            "last_interaction": state.get("last_interaction"),
        }

    @staticmethod
    def mark_field_completed(
        db: Session, client: Client, field_group: str
    ) -> dict:
        """Mark a field group as completed. Advances the onboarding phase.

        Updates last_interaction and session_count.
        """
        state = client.onboarding_state or {}
        completed = state.get("completed_fields", [])
        pending = state.get("pending_fields", [])
        skipped = state.get("skipped_fields", [])

        if field_group not in completed:
            completed.append(field_group)

        # Remove from pending and skipped
        if field_group in pending:
            pending.remove(field_group)
        if field_group in skipped:
            skipped.remove(field_group)

        # Advance phase to next pending or "complete"
        next_group = pending[0] if pending else "complete"

        now = datetime.now(timezone.utc).isoformat()
        state.update({
            "phase": next_group,
            "completed_fields": completed,
            "pending_fields": pending,
            "skipped_fields": skipped,
            "last_interaction": now,
            "session_count": state.get("session_count", 0) + 1,
        })

        client.onboarding_state = state
        # Force SQLAlchemy to detect the JSON mutation
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(client, "onboarding_state")

        db.add(client)
        db.commit()
        db.refresh(client)

        return OnboardingService.get_onboarding_status(client)

    @staticmethod
    def skip_field(db: Session, client: Client, field_group: str) -> dict:
        """Skip a field group. Moves it to skipped_fields for later reminder.

        Advances past the skipped field to the next pending one.
        """
        state = client.onboarding_state or {}
        completed = state.get("completed_fields", [])
        pending = state.get("pending_fields", [])
        skipped = state.get("skipped_fields", [])

        # Move from pending to skipped
        if field_group in pending:
            pending.remove(field_group)
        if field_group not in skipped:
            skipped.append(field_group)

        # Advance phase
        next_group = pending[0] if pending else "complete"

        now = datetime.now(timezone.utc).isoformat()
        state.update({
            "phase": next_group,
            "completed_fields": completed,
            "pending_fields": pending,
            "skipped_fields": skipped,
            "last_interaction": now,
            "session_count": state.get("session_count", 0) + 1,
        })

        client.onboarding_state = state
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(client, "onboarding_state")

        db.add(client)
        db.commit()
        db.refresh(client)

        return OnboardingService.get_onboarding_status(client)

    @staticmethod
    def get_next_question_context(client: Client) -> dict:
        """Return the next field group to ask about with coaching context.

        Returns: field_group name, label, why it matters, fields list.
        Actual industry-specific suggestions come from Claude at runtime.
        """
        status = OnboardingService.get_onboarding_status(client)
        next_group = status.get("next_field_group")

        if next_group is None or next_group == "complete":
            return {
                "field_group": None,
                "label": "Onboarding Complete",
                "why": "All field groups have been addressed.",
                "fields": [],
                "suggestions_placeholder": None,
            }

        # Find the field group config
        group_config = next(
            (f for f in ONBOARDING_FIELDS if f["group"] == next_group),
            None,
        )

        if not group_config:
            return {
                "field_group": next_group,
                "label": next_group,
                "why": "Unknown field group.",
                "fields": [],
                "suggestions_placeholder": None,
            }

        return {
            "field_group": group_config["group"],
            "label": group_config["label"],
            "why": group_config["why"],
            "fields": group_config["fields"],
            "suggestions_placeholder": (
                f"Industry-specific suggestions for {client.industry} "
                f"will be generated by Claude at runtime."
            ),
        }
