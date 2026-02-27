"""Content generation prompt construction: system prompts, few-shot examples,
image prompts.

Builds platform-specific, voice-matched prompts for Claude Code to generate
content drafts. Each prompt includes: voice profile rules, platform constraints,
research context, client intelligence, brand safety guardrails, and AI cliche
avoidance rules.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


# Platform-specific content rules (from locked decisions in CONTEXT.md)
PLATFORM_RULES: dict[str, dict[str, dict[str, Any]]] = {
    "instagram": {
        "feed": {
            "max_chars": 2200,
            "hashtag_guidance": "3-5 highly relevant hashtags (mix of popular and niche)",
            "image_ratio": "1:1 or 4:5",
            "tone_shift": "visual, casual, community-oriented",
        },
        "story": {
            "max_chars": 120,
            "hashtag_guidance": "0-1 hashtag",
            "image_ratio": "9:16",
            "tone_shift": "punchy, conversational, 1-2 lines max for overlay",
        },
    },
    "facebook": {
        "feed": {
            "max_chars": 63206,
            "hashtag_guidance": "0-3 hashtags maximum",
            "image_ratio": "1.91:1 or 1:1",
            "tone_shift": "informational, slightly more formal than Instagram",
        },
    },
}


def build_generation_prompt(
    voice_profile: dict,
    approved_examples: list[str],
    research_findings: Any,
    intelligence: Any,
    platform: str,
    content_type: str,
    client_config: dict,
) -> tuple[str, str]:
    """Construct system prompt and few-shot examples for content generation.

    Args:
        voice_profile: Voice profile data dict (base_voice, platform_variants).
        approved_examples: List of approved post texts for few-shot.
        research_findings: Current research findings (list of dicts or objects).
        intelligence: Client intelligence profile (dict or object).
        platform: Target platform ("facebook" or "instagram").
        content_type: Content type ("feed" or "story").
        client_config: Client configuration dict (guardrails, content_pillars, etc.).

    Returns:
        Tuple of (system_prompt, examples_text).
    """
    rules = PLATFORM_RULES.get(platform, {}).get(content_type, {})

    # Build system prompt sections
    sections: list[str] = []

    # 1. Business identity
    business_name = _extract_business_name(intelligence)
    sections.append(f"You are writing social media content for {business_name}.")

    # 2. Voice style rules
    voice_section = _build_voice_section(voice_profile, platform, content_type)
    sections.append(voice_section)

    # 3. Platform constraints
    platform_section = _build_platform_section(rules, platform, content_type)
    sections.append(platform_section)

    # 4. Brand safety guardrails
    guardrails = client_config.get("guardrails", {})
    if guardrails:
        guardrail_section = _build_guardrail_section(guardrails)
        sections.append(guardrail_section)

    # 5. Content pillar definitions
    pillars = client_config.get("content_pillars", [])
    if pillars:
        pillar_text = ", ".join(str(p) for p in pillars)
        sections.append(
            f"Content pillars for this client: {pillar_text}. "
            "Vary content across these pillars for intentional variety."
        )

    # 6. Research context (inspiration, not citation)
    research_section = _build_research_section(research_findings)
    if research_section:
        sections.append(research_section)

    # 7. Client intelligence context
    intel_section = _build_intelligence_section(intelligence)
    if intel_section:
        sections.append(intel_section)

    # 8. Calendar awareness
    calendar_section = _build_calendar_section(client_config)
    if calendar_section:
        sections.append(calendar_section)

    # 9. Generation rules (AI cliche avoidance, emoji preferences, etc.)
    gen_rules = _build_generation_rules(voice_profile, client_config)
    sections.append(gen_rules)

    system_prompt = "\n\n".join(sections)

    # Build few-shot examples
    examples_text = _build_examples_text(approved_examples)

    return (system_prompt, examples_text)


def build_batch_prompts(
    research: Any,
    intelligence: Any,
    voice: dict,
    platforms: list[str],
    option_count: int,
    include_stories: bool,
    client_config: dict,
    approved_examples: list[str],
) -> list[dict]:
    """Build prompts for a full content generation batch across platforms.

    Args:
        research: Current research findings.
        intelligence: Client intelligence profile.
        voice: Voice profile data dict.
        platforms: List of platforms to generate for.
        option_count: Number of options to generate per platform/type.
        include_stories: Whether to include Instagram stories.
        client_config: Client configuration.
        approved_examples: Approved post texts for few-shot.

    Returns:
        List of prompt dicts with: platform, content_type, system_prompt,
        examples_text, option_count.
    """
    prompts: list[dict] = []

    for platform in platforms:
        # Feed prompt for every platform
        feed_rules = PLATFORM_RULES.get(platform, {}).get("feed")
        if feed_rules:
            system_prompt, examples_text = build_generation_prompt(
                voice_profile=voice,
                approved_examples=approved_examples,
                research_findings=research,
                intelligence=intelligence,
                platform=platform,
                content_type="feed",
                client_config=client_config,
            )
            prompts.append({
                "platform": platform,
                "content_type": "feed",
                "system_prompt": system_prompt,
                "examples_text": examples_text,
                "option_count": option_count,
            })

        # Story prompt for Instagram only
        if include_stories and platform == "instagram":
            story_rules = PLATFORM_RULES.get("instagram", {}).get("story")
            if story_rules:
                system_prompt, examples_text = build_generation_prompt(
                    voice_profile=voice,
                    approved_examples=approved_examples,
                    research_findings=research,
                    intelligence=intelligence,
                    platform="instagram",
                    content_type="story",
                    client_config=client_config,
                )
                prompts.append({
                    "platform": "instagram",
                    "content_type": "story",
                    "system_prompt": system_prompt,
                    "examples_text": examples_text,
                    "option_count": max(1, option_count // 2),
                })

    return prompts


def build_image_prompt(
    business_name: str,
    visual_style: dict,
    platform: str,
    content_type: str,
    post_copy: str,
) -> str:
    """Construct an AI image generation prompt with visual style consistency.

    Args:
        business_name: Client business name.
        visual_style: Visual style guide dict (color_palette, photography_style, etc.).
        platform: Target platform.
        content_type: Content type ("feed" or "story").
        post_copy: The post text for thematic alignment.

    Returns:
        Image generation prompt string. Does NOT include text overlay instructions.
    """
    # Determine aspect ratio
    rules = PLATFORM_RULES.get(platform, {}).get(content_type, {})
    ratio = rules.get("image_ratio", "1:1")
    # Pick the first ratio if multiple offered
    if " or " in ratio:
        ratio = ratio.split(" or ")[0]

    parts: list[str] = []

    # Visual style
    color_palette = visual_style.get("color_palette", "")
    if color_palette:
        parts.append(f"Color palette: {color_palette}.")

    photography_style = visual_style.get("photography_style", "")
    if photography_style:
        parts.append(f"Photography style: {photography_style}.")

    composition = visual_style.get("composition", "")
    if composition:
        parts.append(f"Composition: {composition}.")

    # Thematic context from post copy (first sentence or truncated)
    theme = post_copy[:100].split(".")[0] if post_copy else ""
    if theme:
        parts.append(f"Theme: {theme}.")

    # Aspect ratio
    parts.append(f"Aspect ratio: {ratio}.")

    # Business context
    parts.append(f"For: {business_name}.")

    # Explicit exclusion: no text in image
    parts.append("Do NOT include any text, words, letters, or typography in the image.")

    return " ".join(parts)


# -- Internal helpers --------------------------------------------------------


def _extract_business_name(intelligence: Any) -> str:
    """Extract business name from intelligence profile."""
    if isinstance(intelligence, dict):
        return intelligence.get("business_name", intelligence.get("name", "the business"))
    if hasattr(intelligence, "name"):
        return intelligence.name
    return "the business"


def _build_voice_section(
    voice_profile: dict, platform: str, content_type: str
) -> str:
    """Build voice style instructions from voice profile."""
    parts: list[str] = ["VOICE STYLE:"]

    base_voice = voice_profile.get("base_voice", {})

    # Extract qualitative voice dimensions
    tone = _get_voice_dim(base_voice, "tone")
    formality = _get_voice_dim(base_voice, "formality")
    humor = _get_voice_dim(base_voice, "humor_style")
    vocab = _get_voice_dim(base_voice, "vocabulary_complexity")
    storytelling = _get_voice_dim(base_voice, "storytelling")

    if tone:
        parts.append(f"- Tone: {tone}")
    if formality:
        parts.append(f"- Formality: {formality}")
    if humor:
        parts.append(f"- Humor: {humor}")
    if vocab:
        parts.append(f"- Vocabulary: {vocab}")
    if storytelling:
        parts.append(f"- Storytelling: {storytelling}")

    # Platform-specific voice variant
    variants = voice_profile.get("platform_variants", {})
    platform_variant = variants.get(platform, {})
    if platform_variant:
        parts.append(f"- Platform adjustment: {platform_variant}")

    # Stories get casual shift (locked decision)
    if content_type == "story":
        parts.append("- Story mode: extra casual, punchy, conversational. 1-2 lines max.")

    # Emoji preferences
    emoji_usage = _get_voice_dim(base_voice, "emoji_usage")
    if emoji_usage is not None:
        if str(emoji_usage).lower() in ("none", "no", "false", "0"):
            parts.append("- No emojis. This client does not use emojis.")
        else:
            parts.append(f"- Emoji style: {emoji_usage}")

    return "\n".join(parts)


def _get_voice_dim(base_voice: dict, dim_name: str) -> Optional[str]:
    """Extract a voice dimension value, handling nested {value, confidence} dicts."""
    val = base_voice.get(dim_name)
    if val is None:
        return None
    if isinstance(val, dict):
        v = val.get("value")
        if v is None:
            return None
        return str(v)
    return str(val)


def _build_platform_section(
    rules: dict, platform: str, content_type: str
) -> str:
    """Build platform constraint instructions."""
    parts = [f"PLATFORM RULES ({platform} {content_type}):"]

    max_chars = rules.get("max_chars")
    if max_chars:
        parts.append(f"- Maximum {max_chars} characters")

    hashtag_guide = rules.get("hashtag_guidance")
    if hashtag_guide:
        parts.append(f"- Hashtags: {hashtag_guide}")

    image_ratio = rules.get("image_ratio")
    if image_ratio:
        parts.append(f"- Image aspect ratio: {image_ratio}")

    tone_shift = rules.get("tone_shift")
    if tone_shift:
        parts.append(f"- Tone direction: {tone_shift}")

    return "\n".join(parts)


def _build_guardrail_section(guardrails: dict) -> str:
    """Build brand safety guardrail instructions."""
    parts = ["BRAND SAFETY GUARDRAILS:"]
    parts.append("- No competitor name-drops")
    parts.append("- No unverifiable claims")
    parts.append("- No pricing promises unless explicitly approved")
    parts.append("- No legal-risk language")

    blocklist = guardrails.get("blocklist", [])
    if blocklist:
        parts.append(f"- Blocked topics/words: {', '.join(blocklist)}")

    sensitive = guardrails.get("sensitive_topics", [])
    if sensitive:
        parts.append(f"- Sensitive topics (avoid): {', '.join(sensitive)}")

    return "\n".join(parts)


def _build_research_section(research_findings: Any) -> str:
    """Build research context section (inspired-by, not cited)."""
    if not research_findings:
        return ""

    parts = [
        "CURRENT RESEARCH CONTEXT (use as inspiration, NOT for citation):",
        "Write as the business owner sharing knowledge naturally. "
        "Never reference sources, studies, or articles. All claims must be "
        "supportable by this research context.",
    ]

    # Handle list of findings (dicts or objects)
    findings_list = research_findings if isinstance(research_findings, list) else [research_findings]
    for i, finding in enumerate(findings_list[:10], 1):
        if isinstance(finding, dict):
            topic = finding.get("topic", "")
            summary = finding.get("summary", "")
            angles = finding.get("content_angles", [])
        else:
            topic = getattr(finding, "topic", "")
            summary = getattr(finding, "summary", "")
            angles = getattr(finding, "content_angles", []) or []

        if topic or summary:
            line = f"- {topic}: {summary}"
            if angles:
                line += f" (angles: {', '.join(str(a) for a in angles)})"
            parts.append(line)

    return "\n".join(parts)


def _build_intelligence_section(intelligence: Any) -> str:
    """Build client intelligence context section."""
    if not intelligence:
        return ""

    parts = ["CLIENT INTELLIGENCE:"]

    if isinstance(intelligence, dict):
        desc = intelligence.get("business_description", "")
        if desc:
            parts.append(f"- Business: {desc}")

        audience = intelligence.get("target_audience", {})
        if audience:
            parts.append(f"- Target audience: {audience}")

        geography = intelligence.get("geography_area", "")
        if geography:
            parts.append(f"- Location: {geography}")

        industry = intelligence.get("industry", "")
        if industry:
            parts.append(f"- Industry: {industry}")
    else:
        if hasattr(intelligence, "business_description") and intelligence.business_description:
            parts.append(f"- Business: {intelligence.business_description}")
        if hasattr(intelligence, "target_audience") and intelligence.target_audience:
            parts.append(f"- Target audience: {intelligence.target_audience}")
        if hasattr(intelligence, "geography_area") and intelligence.geography_area:
            parts.append(f"- Location: {intelligence.geography_area}")
        if hasattr(intelligence, "industry") and intelligence.industry:
            parts.append(f"- Industry: {intelligence.industry}")

    return "\n".join(parts) if len(parts) > 1 else ""


def _build_calendar_section(client_config: dict) -> str:
    """Build calendar awareness section from client events."""
    events = client_config.get("upcoming_events", [])
    if not events:
        return ""

    parts = ["UPCOMING EVENTS (factor into content):"]
    for event in events[:5]:
        if isinstance(event, dict):
            name = event.get("name", "")
            date = event.get("date", "")
            parts.append(f"- {name} ({date})")
        else:
            parts.append(f"- {event}")

    return "\n".join(parts)


def _build_generation_rules(voice_profile: dict, client_config: dict) -> str:
    """Build universal generation rules (AI cliche avoidance, etc.)."""
    parts = ["GENERATION RULES:"]
    parts.append("- Write as the business owner, first person where natural")
    parts.append("- Never cite sources, studies, or articles")
    parts.append("- Never use AI cliches: 'In today's fast-paced world', 'Let's dive in', "
                 "'game-changer', 'unlock', 'leverage', 'elevate', 'revolutionize'")
    parts.append("- Avoid starting with questions unless that's the client's established pattern")
    parts.append("- All claims must be supportable by the research context provided")
    parts.append("- Each post must be self-contained and valuable on its own")

    # Emoji preference
    base_voice = voice_profile.get("base_voice", {})
    emoji_usage = _get_voice_dim(base_voice, "emoji_usage")
    if emoji_usage is not None and str(emoji_usage).lower() in ("none", "no", "false", "0"):
        parts.append("- No emojis. This client does not use emojis in their content.")

    return "\n".join(parts)


def _build_examples_text(approved_examples: list[str]) -> str:
    """Format approved posts as numbered few-shot examples."""
    if not approved_examples:
        return ""

    parts = ["APPROVED CONTENT EXAMPLES (match this voice):"]
    for i, example in enumerate(approved_examples[:5], 1):
        parts.append(f"\nExample {i}:\n{example}")

    return "\n".join(parts)
