#!/usr/bin/env python3
"""Shared Anthropic API response helpers."""

from __future__ import annotations

import json


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


def message_text_from_response(response, *, context: str) -> str:
    raise_for_anthropic_status(response, context=context)
    payload = response.json()
    content = payload.get("content")
    if not isinstance(content, list) or not content:
        raise RuntimeError(f"{context} returned an unexpected response shape: missing content")
    first = content[0]
    if not isinstance(first, dict) or "text" not in first:
        raise RuntimeError(f"{context} returned an unexpected response shape: missing content[0].text")
    return str(first["text"])
