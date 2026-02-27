"""AI-assisted labeling compliance: platform-specific rules and auto-application.

Sophia applies AI-assisted labeling when platforms mandate it.
Default OFF for text-only Meta posts until regulations require it.
Built as configurable rules so the system is ready when EU AI Act
(August 2026) or platform policy changes require text labels.

Current policy (Feb 2026):
- Meta (Facebook/Instagram): AI label required ONLY for AI-generated
  photorealistic images and realistic audio. Text-only posts do NOT
  require AI labeling.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sophia.content.models import ContentDraft


# Platform-specific AI labeling rules
# Configurable: update when regulations change
AI_LABEL_RULES: dict[str, dict] = {
    "facebook": {
        "text_only": False,  # Meta does NOT currently require AI label for text-only posts
        "photorealistic_image": True,  # Required for AI-generated photorealistic images
        "realistic_audio": True,  # Required for AI-generated realistic audio
        "label_field": "ai_generated",  # Meta API field for AI disclosure
    },
    "instagram": {
        "text_only": False,  # Same as Facebook (both Meta platforms)
        "photorealistic_image": True,
        "realistic_audio": True,
        "label_field": "ai_generated",
    },
}


def should_apply_ai_label(
    platform: str, content_type: str, has_ai_image: bool = False
) -> bool:
    """Determine whether AI labeling is required for this content.

    Args:
        platform: Target platform ("facebook" or "instagram").
        content_type: Content type ("feed" or "story").
        has_ai_image: Whether the post includes an AI-generated
            photorealistic image.

    Returns:
        True if AI label should be applied, False otherwise.
    """
    rules = AI_LABEL_RULES.get(platform.lower())
    if rules is None:
        # Unknown platform -- default to labeling for safety
        return True

    # Text-only posts: check platform rule
    if not has_ai_image:
        return rules.get("text_only", False)

    # Posts with AI-generated photorealistic images
    return rules.get("photorealistic_image", True)


def apply_ai_label(draft: "ContentDraft") -> "ContentDraft":
    """Apply AI-assisted label to a content draft.

    Sets has_ai_label=True and could add metadata indicating
    the reason (regulatory requirement or platform policy).

    Args:
        draft: The content draft to label.

    Returns:
        The modified draft with AI label applied.
    """
    draft.has_ai_label = True
    return draft


def get_label_requirements_summary() -> dict:
    """Return human-readable summary of current AI label requirements per platform.

    Useful for operator reference and transparency about what gets labeled.

    Returns:
        Dict mapping platform name to requirement description.
    """
    summary: dict[str, dict] = {}

    for platform, rules in AI_LABEL_RULES.items():
        text_required = rules.get("text_only", False)
        image_required = rules.get("photorealistic_image", True)
        audio_required = rules.get("realistic_audio", True)

        description_parts = []
        if text_required:
            description_parts.append("Text-only posts: REQUIRED")
        else:
            description_parts.append("Text-only posts: Not required")

        if image_required:
            description_parts.append("AI photorealistic images: REQUIRED")
        else:
            description_parts.append("AI photorealistic images: Not required")

        if audio_required:
            description_parts.append("AI realistic audio: REQUIRED")
        else:
            description_parts.append("AI realistic audio: Not required")

        summary[platform] = {
            "text_only_required": text_required,
            "photorealistic_image_required": image_required,
            "realistic_audio_required": audio_required,
            "label_field": rules.get("label_field", ""),
            "description": "; ".join(description_parts),
        }

    return summary
