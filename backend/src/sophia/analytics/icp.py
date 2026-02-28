"""ICP (Ideal Customer Profile) audience comparison.

Compares actual Instagram audience demographics against client target
audience personas. Provides match percentages per persona dimension
(age, gender, location).

Async pull_audience_demographics uses httpx for Instagram Graph API.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v22.0"


async def pull_audience_demographics(
    ig_user_id: str, access_token: str
) -> dict:
    """Pull Instagram audience demographics via Graph API.

    GET /{ig_user_id}/insights?metric=follower_demographics&period=lifetime
        &metric_type=total_value&breakdown=age,city,country,gender

    Args:
        ig_user_id: Instagram business account ID.
        access_token: Meta Graph API access token.

    Returns:
        Structured dict: {age: {range: pct}, gender: {label: pct},
        city: {name: pct}, country: {code: pct}}.
        Returns empty dict on error.
    """
    url = f"{GRAPH_API_BASE}/{ig_user_id}/insights"
    params = {
        "metric": "follower_demographics",
        "period": "lifetime",
        "metric_type": "total_value",
        "access_token": access_token,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        return _parse_demographics_response(data)

    except Exception as e:
        logger.error("Error pulling audience demographics: %s", e)
        return {}


def _parse_demographics_response(data: dict) -> dict:
    """Parse Meta API demographics response into structured dict.

    The API returns multiple breakdowns within the data array.
    Each breakdown type has a different structure.
    """
    result: dict = {"age": {}, "gender": {}, "city": {}, "country": {}}

    items = data.get("data", [])
    for item in items:
        total_value = item.get("total_value", {})
        breakdowns = total_value.get("breakdowns", [])

        for breakdown in breakdowns:
            dimension = breakdown.get("dimension_keys", [""])[0]
            results_list = breakdown.get("results", [])

            total = sum(r.get("value", 0) for r in results_list)
            if total == 0:
                continue

            for result_item in results_list:
                keys = result_item.get("dimension_values", [])
                value = result_item.get("value", 0)
                pct = round(value / total * 100, 1)

                key = keys[0] if keys else "unknown"

                if dimension in ("age", "age_range"):
                    result["age"][key] = pct
                elif dimension == "gender":
                    result["gender"][key] = pct
                elif dimension == "city":
                    result["city"][key] = pct
                elif dimension == "country":
                    result["country"][key] = pct

    return result


def compare_audience_to_icp(
    actual_demographics: dict, client_target_audience: dict
) -> dict:
    """Compare actual audience demographics against client ICP personas.

    For each persona in target_audience:
    - Age match: overlap between persona age range and actual distribution
    - Gender match: persona gender preference vs actual split
    - Location match: persona geography vs actual city/country distribution

    Args:
        actual_demographics: Dict from pull_audience_demographics or similar.
            Expected keys: age, gender, city, country.
        client_target_audience: Client.target_audience JSON field.
            Expected format: {"personas": [{"name": ..., "age_range": ...,
            "gender": ..., "location": ...}]}

    Returns:
        Dict with per-persona match percentages and overall_icp_fit.
    """
    if not actual_demographics or not client_target_audience:
        return {"personas": {}, "overall_icp_fit": 0.0}

    personas = client_target_audience.get("personas", [])
    if not personas:
        # Try treating the whole dict as a single persona if no personas key
        if "name" in client_target_audience:
            personas = [client_target_audience]
        else:
            return {"personas": {}, "overall_icp_fit": 0.0}

    actual_age = actual_demographics.get("age", {})
    actual_gender = actual_demographics.get("gender", {})
    actual_city = actual_demographics.get("city", {})
    actual_country = actual_demographics.get("country", {})

    persona_results = {}
    fit_scores = []

    for persona in personas:
        name = persona.get("name", "Unknown")

        # Age match
        age_match = _compute_age_match(
            persona.get("age_range", ""), actual_age
        )

        # Gender match
        gender_match = _compute_gender_match(
            persona.get("gender", ""), actual_gender
        )

        # Location match
        location_match = _compute_location_match(
            persona.get("location", ""), actual_city, actual_country
        )

        # Overall persona match (equal weight)
        scores = [age_match, gender_match, location_match]
        valid_scores = [s for s in scores if s is not None]
        overall = round(sum(valid_scores) / len(valid_scores), 1) if valid_scores else 0.0

        persona_results[name] = {
            "age_match_pct": age_match or 0.0,
            "gender_match_pct": gender_match or 0.0,
            "location_match_pct": location_match or 0.0,
            "overall_match_pct": overall,
        }
        fit_scores.append(overall)

    overall_fit = round(sum(fit_scores) / len(fit_scores), 1) if fit_scores else 0.0

    return {
        "personas": persona_results,
        "overall_icp_fit": overall_fit,
    }


def _compute_age_match(
    persona_age_range: str, actual_age: dict
) -> Optional[float]:
    """Compute overlap between persona age range and actual distribution.

    persona_age_range format: "25-44" or "18-34"
    actual_age dict: {"18-24": 15.0, "25-34": 30.0, ...}
    """
    if not persona_age_range or not actual_age:
        return None

    try:
        parts = persona_age_range.replace("+", "-999").split("-")
        target_min = int(parts[0])
        target_max = int(parts[1]) if len(parts) > 1 else 999
    except (ValueError, IndexError):
        return None

    overlap_pct = 0.0
    for age_range_str, pct in actual_age.items():
        try:
            range_parts = age_range_str.replace("+", "-999").split("-")
            range_min = int(range_parts[0])
            range_max = int(range_parts[1]) if len(range_parts) > 1 else 999
        except (ValueError, IndexError):
            continue

        # Check if ranges overlap
        if range_min <= target_max and range_max >= target_min:
            overlap_pct += pct

    return round(min(overlap_pct, 100.0), 1)


def _compute_gender_match(
    persona_gender: str, actual_gender: dict
) -> Optional[float]:
    """Compute gender match between persona preference and actual split.

    persona_gender: "female", "male", "all", or ""
    actual_gender: {"F": 60.0, "M": 40.0}
    """
    if not persona_gender or not actual_gender:
        return None

    gender_lower = persona_gender.lower()
    if gender_lower in ("all", "any", ""):
        return 100.0

    # Map persona gender to actual gender keys
    gender_map = {
        "female": ["F", "female", "f"],
        "male": ["M", "male", "m"],
    }

    target_keys = gender_map.get(gender_lower, [gender_lower])

    match_pct = 0.0
    for key, pct in actual_gender.items():
        if key.lower() in [k.lower() for k in target_keys]:
            match_pct += pct

    return round(min(match_pct, 100.0), 1)


def _compute_location_match(
    persona_location: str,
    actual_city: dict,
    actual_country: dict,
) -> Optional[float]:
    """Compute location match between persona geography and actual distribution.

    persona_location: city name, region, or country
    actual_city: {"Toronto": 25.0, ...}
    actual_country: {"CA": 80.0, ...}
    """
    if not persona_location:
        return None

    loc_lower = persona_location.lower()

    # Check cities first
    if actual_city:
        match_pct = 0.0
        for city, pct in actual_city.items():
            if loc_lower in city.lower() or city.lower() in loc_lower:
                match_pct += pct
        if match_pct > 0:
            return round(min(match_pct, 100.0), 1)

    # Check countries
    if actual_country:
        match_pct = 0.0
        for country, pct in actual_country.items():
            if loc_lower in country.lower() or country.lower() in loc_lower:
                match_pct += pct
        if match_pct > 0:
            return round(min(match_pct, 100.0), 1)

    return 0.0
