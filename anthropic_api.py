#!/usr/bin/env python3
"""Shared Anthropic API response helpers."""

from __future__ import annotations

import json
import os
import sys
from typing import Any


PROMPT_CACHE_TTL = "5m"
USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)


def ephemeral_cache_control(*, ttl: str = PROMPT_CACHE_TTL) -> dict[str, str]:
    return {"type": "ephemeral", "ttl": ttl}


def text_block(text: str, *, cache: bool = False, ttl: str = PROMPT_CACHE_TTL) -> dict[str, Any]:
    block: dict[str, Any] = {"type": "text", "text": text}
    if cache:
        if not text.strip():
            raise ValueError("Cannot attach cache_control to an empty text block")
        block["cache_control"] = ephemeral_cache_control(ttl=ttl)
    return block


def enable_automatic_prompt_cache(payload: dict[str, Any], *, ttl: str = PROMPT_CACHE_TTL) -> dict[str, Any]:
    payload["cache_control"] = ephemeral_cache_control(ttl=ttl)
    return payload


def extract_error_message(response) -> str:
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError):
        payload = None

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            error_type = str(error.get("type", "")).strip()
            message = str(error.get("message", "")).strip()
            if error_type and message:
                return f"{error_type}: {message}"
            if message:
                return message
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()

    body = response.text.strip()
    return body or f"HTTP {response.status_code}"


def _extra_hint(detail: str) -> str:
    lowered = detail.lower()
    if "credit balance is too low" in lowered or "plans & billing" in lowered:
        return " Anthropic API credits are required for this repo; a Claude Max subscription does not cover direct API usage."
    if "api key" in lowered and ("invalid" in lowered or "missing" in lowered):
        return " Check ANTHROPIC_API_KEY in .env."
    return ""


def raise_for_anthropic_status(response, *, context: str) -> None:
    import httpx

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = extract_error_message(response)
        raise RuntimeError(f"{context} failed ({response.status_code}): {detail}{_extra_hint(detail)}") from exc


def extract_usage(payload: object) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return {}
    normalized: dict[str, int] = {}
    for field in USAGE_FIELDS:
        try:
            normalized[field] = int(usage.get(field, 0) or 0)
        except (TypeError, ValueError):
            normalized[field] = 0
    return normalized


def _should_log_usage(usage: dict[str, int]) -> bool:
    env_value = os.environ.get("AUTONOVEL_LOG_ANTHROPIC_USAGE", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    return bool(usage.get("cache_creation_input_tokens") or usage.get("cache_read_input_tokens"))


def log_response_usage(payload: object, *, context: str) -> None:
    usage = extract_usage(payload)
    if not usage or not _should_log_usage(usage):
        return
    print(
        (
            f"[anthropic] {context}: input={usage['input_tokens']} "
            f"output={usage['output_tokens']} "
            f"cache_write={usage['cache_creation_input_tokens']} "
            f"cache_read={usage['cache_read_input_tokens']}"
        ),
        file=sys.stderr,
    )


def response_payload(response, *, context: str) -> dict[str, Any]:
    raise_for_anthropic_status(response, context=context)
    try:
        payload = response.json()
    except (ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{context} returned invalid JSON") from exc
    log_response_usage(payload, context=context)
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context} returned an unexpected response shape")
    return payload


def message_text_from_response(response, *, context: str) -> str:
    payload = response_payload(response, context=context)
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError(f"{context} returned an unexpected response shape: missing content")
    first = content[0]
    if not isinstance(first, dict) or "text" not in first:
        raise RuntimeError(f"{context} returned an unexpected response shape: missing content[0].text")
    return str(first["text"])
