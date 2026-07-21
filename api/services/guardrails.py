"""Agno input guardrails for Chat / Team / Workflow agents.

Uses built-in Agno pre-hooks only (no OpenAI Moderation):

- :class:`agno.guardrails.PIIDetectionGuardrail`
- :class:`agno.guardrails.PromptInjectionGuardrail`

See https://docs.agno.com/guardrails/overview
"""

from __future__ import annotations

from typing import Any

from agno.exceptions import CheckTrigger, InputCheckError
from agno.guardrails import PIIDetectionGuardrail, PromptInjectionGuardrail
from loguru import logger

from api.config import get_settings

# User-facing Chinese messages (SSE / audit). Keep codes stable for clients.
_GUARDRAIL_MESSAGES: dict[str, str] = {
    CheckTrigger.PII_DETECTED.value: (
        "输入疑似包含个人敏感信息（PII），已拦截。请脱敏后再试。"
    ),
    CheckTrigger.PROMPT_INJECTION.value: (
        "输入疑似包含提示注入或越狱尝试，已拦截。"
    ),
    CheckTrigger.INPUT_NOT_ALLOWED.value: "输入未通过安全护栏校验，已拦截。",
}


def is_guardrails_enabled() -> bool:
    return bool(get_settings().guardrails_enabled)


def build_input_guardrails() -> list[Any]:
    """Return Agno ``pre_hooks`` list (empty when disabled).

    Never includes OpenAI Moderation Guardrail.
    """
    if not is_guardrails_enabled():
        return []
    settings = get_settings()
    hooks: list[Any] = []
    if settings.guardrails_pii_enabled:
        hooks.append(
            PIIDetectionGuardrail(
                mask_pii=bool(settings.guardrails_pii_mask),
                enable_ssn_check=True,
                enable_credit_card_check=True,
                # Chat often includes operator emails; keep off by default for mask mode
                # or when operators paste contact info — SSN/CC are higher risk.
                enable_email_check=bool(settings.guardrails_pii_check_email),
                enable_phone_check=bool(settings.guardrails_pii_check_phone),
            )
        )
    if settings.guardrails_prompt_injection_enabled:
        hooks.append(PromptInjectionGuardrail())
    return hooks


def apply_guardrails_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Merge input guardrails into Agent/Team constructor kwargs."""
    hooks = build_input_guardrails()
    if not hooks:
        return kwargs
    existing = kwargs.get("pre_hooks")
    if existing is None:
        kwargs["pre_hooks"] = list(hooks)
    elif isinstance(existing, list):
        kwargs["pre_hooks"] = [*hooks, *existing]
    else:
        kwargs["pre_hooks"] = [*hooks, existing]
    return kwargs


def is_input_check_error(exc: BaseException | Exception) -> bool:
    return isinstance(exc, InputCheckError)


def guardrail_failure_payload(exc: BaseException | Exception) -> dict[str, Any]:
    """Map :class:`InputCheckError` to workbench ``run.failed`` fields."""
    if not isinstance(exc, InputCheckError):
        return {
            "code": "AGENT_RUN_ERROR",
            "message": str(exc) or "运行失败",
            "retryable": True,
        }
    trigger = getattr(exc, "check_trigger", None)
    error_id = getattr(exc, "error_id", None) or (
        trigger.value if isinstance(trigger, CheckTrigger) else "input_not_allowed"
    )
    message = _GUARDRAIL_MESSAGES.get(
        str(error_id),
        str(getattr(exc, "message", None) or exc) or "输入未通过安全护栏",
    )
    extra = getattr(exc, "additional_data", None)
    payload: dict[str, Any] = {
        "code": f"GUARDRAIL_{str(error_id).upper()}",
        "message": message,
        "retryable": False,
        "check_trigger": str(error_id),
    }
    if isinstance(extra, dict) and extra:
        # Safe projection: only known PII type names, no raw matched text.
        detected = extra.get("detected_pii")
        if isinstance(detected, list):
            payload["detected_pii"] = [str(item) for item in detected[:12]]
    logger.info(
        "Input guardrail blocked run trigger={} message={}",
        error_id,
        message,
    )
    return payload
