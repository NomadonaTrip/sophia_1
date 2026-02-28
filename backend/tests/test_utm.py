"""Tests for UTM parameter builder.

Validates URL construction, existing param preservation, UTM override,
and injection into post copy text.
"""

from sophia.analytics.utm import build_utm_url, inject_utm_into_copy


class TestBuildUtmUrl:
    """build_utm_url function tests."""

    def test_clean_url(self):
        """Appends UTM params to a URL with no existing query params."""
        result = build_utm_url(
            "https://example.com/page",
            platform="instagram",
            campaign_slug="spring-tips",
            draft_id=42,
        )
        assert "utm_source=instagram" in result
        assert "utm_medium=social" in result
        assert "utm_campaign=spring-tips" in result
        assert "utm_content=post_42" in result
        assert result.startswith("https://example.com/page?")

    def test_preserves_existing_params(self):
        """Preserves non-UTM query params when adding UTM."""
        result = build_utm_url(
            "https://example.com/page?ref=email&lang=en",
            platform="facebook",
            campaign_slug="promo",
            draft_id=7,
        )
        assert "ref=email" in result
        assert "lang=en" in result
        assert "utm_source=facebook" in result
        assert "utm_content=post_7" in result

    def test_overrides_existing_utm(self):
        """Overrides existing UTM params with new values."""
        result = build_utm_url(
            "https://example.com?utm_source=old&utm_campaign=stale",
            platform="instagram",
            campaign_slug="fresh",
            draft_id=99,
        )
        assert "utm_source=instagram" in result
        assert "utm_campaign=fresh" in result
        # Old values should be gone
        assert "utm_source=old" not in result
        assert "utm_campaign=stale" not in result

    def test_preserves_fragment(self):
        """Preserves URL fragment (#section)."""
        result = build_utm_url(
            "https://example.com/page#section",
            platform="facebook",
            campaign_slug="test",
            draft_id=1,
        )
        assert result.endswith("#section") or "#section" in result
        assert "utm_source=facebook" in result

    def test_preserves_path(self):
        """Preserves URL path."""
        result = build_utm_url(
            "https://example.com/blog/my-post",
            platform="facebook",
            campaign_slug="blog",
            draft_id=5,
        )
        assert "/blog/my-post" in result


class TestInjectUtmIntoCopy:
    """inject_utm_into_copy function tests."""

    def test_url_in_text(self):
        """Finds and tags a URL within post copy."""
        copy = "Check out our latest post! https://example.com/blog"
        result = inject_utm_into_copy(
            copy, platform="instagram", campaign_slug="spring", draft_id=10
        )
        assert "utm_source=instagram" in result
        assert "Check out our latest post!" in result

    def test_no_urls_passthrough(self):
        """Returns copy unchanged when no URLs found."""
        copy = "No links here, just a great caption!"
        result = inject_utm_into_copy(
            copy, platform="facebook", campaign_slug="test", draft_id=1
        )
        assert result == copy

    def test_multiple_urls(self):
        """Tags multiple URLs in the same post copy."""
        copy = (
            "Visit https://example.com/page1 and "
            "also https://example.com/page2 for more!"
        )
        result = inject_utm_into_copy(
            copy, platform="facebook", campaign_slug="multi", draft_id=3
        )
        # Both URLs should have UTM params
        assert result.count("utm_source=facebook") == 2
        assert result.count("utm_content=post_3") == 2

    def test_url_at_end_of_sentence(self):
        """Handles URLs at end of text correctly."""
        copy = "Check this out: https://example.com"
        result = inject_utm_into_copy(
            copy, platform="instagram", campaign_slug="test", draft_id=5
        )
        assert "utm_source=instagram" in result
        assert "Check this out:" in result
