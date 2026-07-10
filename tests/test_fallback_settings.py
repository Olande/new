"""Tests for fallback settings configuration."""

from app.core.config.settings import Settings


def test_fallback_settings_defaults():
    """FR-010, FR-012: Fallback settings have correct defaults."""
    settings = Settings()
    assert settings.fallback_enabled is True
    assert settings.fallback_min_result_threshold == 5
    assert settings.fallback_max_results == 20


def test_fallback_settings_env_override(monkeypatch):
    """Settings respect env var overrides."""
    monkeypatch.setenv("FALLBACK_ENABLED", "false")
    monkeypatch.setenv("FALLBACK_MIN_RESULT_THRESHOLD", "3")
    monkeypatch.setenv("FALLBACK_MAX_RESULTS", "10")
    settings = Settings()
    assert settings.fallback_enabled is False
    assert settings.fallback_min_result_threshold == 3
    assert settings.fallback_max_results == 10
