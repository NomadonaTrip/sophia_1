"""Institutional knowledge service: ICP extraction and industry query.

Extracts anonymized knowledge from client profiles during archival.
Stores only industry-level patterns -- no client-identifying information (SAFE-01).
"""

from sqlalchemy.orm import Session

from sophia.institutional.models import InstitutionalKnowledge


class InstitutionalService:
    """ICP knowledge extraction and query for institutional knowledge."""

    @staticmethod
    def extract_from_client(db: Session, client: "Client") -> bool:  # noqa: F821
        """Extract anonymized ICP knowledge from a client profile.

        Creates InstitutionalKnowledge entries for industry patterns.
        Strips all client-identifying information -- only industry, geography type,
        and patterns are retained.

        Returns True if knowledge was extracted, False if insufficient data.
        """
        # Check if there's enough data to extract meaningful patterns
        has_audience = bool(client.target_audience)
        has_pillars = bool(client.content_pillars)

        if not has_audience and not has_pillars:
            return False

        # Extract industry patterns from target audience + content pillars
        content: dict = {}

        if has_audience:
            # Anonymize: keep demographics/psychographics structure, remove names
            audience = client.target_audience
            content["audience_patterns"] = {
                "structure": list(audience.keys()) if isinstance(audience, dict) else [],
                "has_demographics": "demographics" in audience if isinstance(audience, dict) else False,
                "has_psychographics": "psychographics" in audience if isinstance(audience, dict) else False,
            }

        if has_pillars:
            # Keep pillar categories, strip specifics
            pillars = client.content_pillars
            content["content_pillar_count"] = len(pillars) if isinstance(pillars, list) else 0
            content["pillar_types"] = (
                [p.get("type", "general") if isinstance(p, dict) else "text" for p in pillars]
                if isinstance(pillars, list)
                else []
            )

        # Add geography type (not specific location)
        if client.geography_area:
            content["geography_type"] = "local"
        if client.geography_radius_km:
            content["service_radius_category"] = (
                "hyperlocal" if client.geography_radius_km <= 10
                else "local" if client.geography_radius_km <= 50
                else "regional"
            )

        # Check if we already have knowledge for this industry
        existing = (
            db.query(InstitutionalKnowledge)
            .filter(
                InstitutionalKnowledge.industry == client.industry,
                InstitutionalKnowledge.knowledge_type == "industry_patterns",
            )
            .first()
        )

        if existing:
            # Merge content and increment source count
            merged = existing.content or {}
            merged.update(content)
            existing.content = merged
            existing.source_client_count += 1
            # Confidence increases with more data sources
            existing.confidence_score = min(
                1.0, existing.confidence_score + 0.1
            )
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(existing, "content")
            db.add(existing)
        else:
            # Create new entry
            knowledge = InstitutionalKnowledge(
                knowledge_type="industry_patterns",
                industry=client.industry,
                content=content,
                source_client_count=1,
                confidence_score=0.5,
            )
            db.add(knowledge)

        db.flush()
        return True

    @staticmethod
    def query_industry_knowledge(
        db: Session, industry: str
    ) -> list[InstitutionalKnowledge]:
        """Return all institutional knowledge for a given industry.

        Used during onboarding for industry-specific coaching suggestions.
        No client_id filtering needed -- this table has no client references.
        """
        return (
            db.query(InstitutionalKnowledge)
            .filter(InstitutionalKnowledge.industry == industry)
            .order_by(InstitutionalKnowledge.confidence_score.desc())
            .all()
        )
