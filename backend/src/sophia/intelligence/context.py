"""Context switching with fuzzy match and smart summary.

Handles switching between clients using fuzzy name matching,
providing smart summaries, and portfolio-level overviews.
"""

from datetime import datetime, timezone
from typing import Optional

from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from sophia.exceptions import ClientNotFoundError
from sophia.intelligence.models import Client, VoiceProfile
from sophia.intelligence.onboarding import OnboardingService
from sophia.intelligence.schemas import ClientRosterItem


class ContextService:
    """Context switching with fuzzy match, smart summary, and portfolio overview."""

    @staticmethod
    def switch_context(
        db: Session, query: str, client_names: list[str] | None = None
    ) -> dict:
        """Switch context to a client using fuzzy name matching.

        - Single match above 90: auto-switch, return client summary.
        - Multiple matches (70-90): return candidates for disambiguation.
        - No match: raise ClientNotFoundError.

        On successful switch: updates last_activity_at on the target client.
        """
        # Get all active client names if not provided
        if client_names is None:
            clients = (
                db.query(Client)
                .filter(Client.is_archived == False)  # noqa: E712
                .all()
            )
            client_names = [c.name for c in clients]

        if not client_names:
            raise ClientNotFoundError(
                message="No active clients found",
                suggestion="Create a client first using the onboarding flow",
            )

        # Use rapidfuzz extract to find matches
        matches = process.extract(
            query,
            client_names,
            scorer=fuzz.WRatio,
            limit=5,
        )

        # Filter matches above threshold 70
        candidates = [(name, score) for name, score, _ in matches if score >= 70]

        if not candidates:
            raise ClientNotFoundError(
                message=f"No client found matching '{query}'",
                detail=f"Best match: {matches[0][0]} ({matches[0][1]:.0f}%)" if matches else "No clients in roster",
                suggestion="Check the roster for correct client names",
            )

        # Single strong match (>= 90)
        top_name, top_score = candidates[0]
        if top_score >= 90:
            client = db.query(Client).filter(Client.name == top_name).first()
            if client:
                client.last_activity_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(client)
                summary = ContextService.get_smart_summary(db, client)
                return {
                    "status": "switched",
                    "client_id": client.id,
                    "client_name": client.name,
                    "match_score": top_score,
                    "summary": summary,
                }

        # Multiple ambiguous matches (70-90) or top match exactly at 70-89
        if len(candidates) > 1 or top_score < 90:
            return {
                "status": "disambiguation_needed",
                "candidates": [
                    {"name": name, "score": score} for name, score in candidates
                ],
                "query": query,
            }

        # Fallback: single candidate below 90 -- still offer it
        return {
            "status": "disambiguation_needed",
            "candidates": [
                {"name": name, "score": score} for name, score in candidates
            ],
            "query": query,
        }

    @staticmethod
    def get_smart_summary(db: Session, client: Client) -> dict:
        """Return a smart summary for context switch display.

        Includes: name, industry, completeness, MVP readiness, last activity,
        pending onboarding, voice confidence, and actionable alerts.
        """
        # Onboarding status
        onboarding = OnboardingService.get_onboarding_status(client)

        # Voice profile confidence
        voice = (
            db.query(VoiceProfile)
            .filter(VoiceProfile.client_id == client.id)
            .first()
        )
        voice_confidence = voice.overall_confidence_pct if voice else 0

        # Build actionable alerts
        alerts: list[str] = []

        if voice_confidence == 0:
            alerts.append("No voice profile -- content generation will be generic")
        elif voice_confidence < 50:
            alerts.append(
                f"Voice profile is low confidence ({voice_confidence}%) -- "
                "provide more materials or run calibration"
            )

        if not client.content_pillars:
            alerts.append("Missing content pillars -- needed for MVP readiness")

        if onboarding.get("pending_fields"):
            pending_count = len(onboarding["pending_fields"])
            alerts.append(
                f"Onboarding incomplete -- {pending_count} field group(s) remaining"
            )

        if not client.is_mvp_ready:
            alerts.append("Not MVP-ready -- cannot generate content yet")

        return {
            "name": client.name,
            "industry": client.industry,
            "profile_completeness_pct": client.profile_completeness_pct,
            "is_mvp_ready": client.is_mvp_ready,
            "last_activity_at": (
                client.last_activity_at.isoformat()
                if client.last_activity_at
                else None
            ),
            "last_action_summary": client.last_action_summary,
            "pending_onboarding_fields": onboarding.get("pending_fields", []),
            "voice_confidence_pct": voice_confidence,
            "actionable_alerts": alerts,
        }

    @staticmethod
    def get_portfolio_overview(db: Session) -> dict:
        """Return portfolio-level overview for session-start briefing.

        Includes: total, active, onboarding, archived counts, and roster.
        """
        all_clients = db.query(Client).all()

        total = len(all_clients)
        archived = sum(1 for c in all_clients if c.is_archived)
        active = total - archived

        # Clients still in onboarding (have pending fields)
        onboarding_count = 0
        for c in all_clients:
            if not c.is_archived and c.onboarding_state:
                pending = c.onboarding_state.get("pending_fields", [])
                if pending:
                    onboarding_count += 1

        roster = [
            ClientRosterItem(
                id=c.id,
                name=c.name,
                industry=c.industry,
                profile_completeness_pct=c.profile_completeness_pct,
                is_mvp_ready=c.is_mvp_ready,
                is_archived=c.is_archived,
                last_activity_at=c.last_activity_at,
            )
            for c in all_clients
        ]

        return {
            "total_clients": total,
            "active_clients": active,
            "onboarding_clients": onboarding_count,
            "archived_clients": archived,
            "roster": roster,
        }
