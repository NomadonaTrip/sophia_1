"""UTM parameter builder for tracking social media content performance.

Appends standard UTM parameters to URLs in post copy before publishing.
Uses utm_source={platform}, utm_medium=social, utm_campaign={slug},
utm_content=post_{draft_id}.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

# Regex for finding HTTP/HTTPS URLs in post copy
_URL_PATTERN = re.compile(r"https?://[^\s<>\"')\]]+")


def build_utm_url(
    base_url: str,
    platform: str,
    campaign_slug: str,
    draft_id: int,
) -> str:
    """Append UTM parameters to a URL.

    Preserves existing query params. Overrides any existing UTM params
    to ensure consistent tracking.

    Args:
        base_url: The URL to append UTM params to.
        platform: Social platform (e.g. "facebook", "instagram").
        campaign_slug: Campaign slug for utm_campaign.
        draft_id: Content draft ID for utm_content.

    Returns:
        URL with UTM params appended.
    """
    parsed = urlparse(base_url)
    existing_params = parse_qs(parsed.query, keep_blank_values=True)

    # Build UTM params (override any existing)
    utm_params = {
        "utm_source": platform,
        "utm_medium": "social",
        "utm_campaign": campaign_slug,
        "utm_content": f"post_{draft_id}",
    }

    # Merge: existing params first, UTM overrides
    merged = {}
    for key, values in existing_params.items():
        if not key.startswith("utm_"):
            merged[key] = values[0] if len(values) == 1 else values
    merged.update(utm_params)

    new_query = urlencode(merged, doseq=True)
    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment,
    ))


def inject_utm_into_copy(
    copy: str,
    platform: str,
    campaign_slug: str,
    draft_id: int,
) -> str:
    """Find URLs in post copy and append UTM parameters to each.

    If no URLs found, returns copy unchanged.

    Args:
        copy: Post copy text.
        platform: Social platform.
        campaign_slug: Campaign slug for utm_campaign.
        draft_id: Content draft ID for utm_content.

    Returns:
        Copy with UTM-tagged URLs.
    """
    def _replace_url(match: re.Match) -> str:
        url = match.group(0)
        return build_utm_url(url, platform, campaign_slug, draft_id)

    return _URL_PATTERN.sub(_replace_url, copy)
