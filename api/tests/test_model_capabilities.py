from api.services.model_capabilities import (
    apply_optimal_model_defaults,
    capabilities_for,
    public_capabilities,
    resolve_reasoning_effort,
)


def test_xai_has_no_reasoning_effort_but_live_search():
    caps = capabilities_for("xai", model_id="grok-4.5")
    assert caps.supports_reasoning_effort is False
    assert caps.supports_live_search is True
    assert caps.reasoning_via_model_id is True
    assert caps.optimal_api_protocol == "chat-completions"
    assert resolve_reasoning_effort(provider="xai", override="high") is None
    pub = public_capabilities("xai", model_id="grok-4-1-fast-non-reasoning-latest")
    assert pub["xai_non_reasoning_model"] is True


def test_resolve_prefers_override_then_configured_then_optimal():
    assert resolve_reasoning_effort(provider="deepseek", override="high", configured="max") == "high"
    assert resolve_reasoning_effort(provider="deepseek", override="nope", configured="max") == "max"
    assert resolve_reasoning_effort(provider="deepseek", override="nope", configured="nope") == "max"
    assert (
        resolve_reasoning_effort(
            provider="openai",
            api_protocol="chat-completions",
            override="minimal",
            configured="low",
        )
        == "low"
    )


def test_apply_optimal_fills_missing_only():
    raw = apply_optimal_model_defaults({"provider": "openai", "structured_output_mode": "json"})
    assert raw["api_protocol"] == "responses"
    assert raw["structured_output_mode"] == "json"  # preserved
    assert raw["default_reasoning_effort"] == "high"
    assert raw["retries"] == 4
