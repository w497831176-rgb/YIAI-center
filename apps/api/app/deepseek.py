from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import settings
from .db import new_id


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def price_snapshot(model: str) -> dict[str, Any]:
    if model != "deepseek-v4-flash":
        raise ValueError("Ordinary runtime cannot select the expert model")
    return {
        "currency": "USD",
        "unit": "per_1m_tokens",
        "cache_hit_input": settings.flash_cache_hit_usd_per_m,
        "cache_miss_input": settings.flash_cache_miss_usd_per_m,
        "output": settings.flash_output_usd_per_m,
        "source": "https://api-docs.deepseek.com/quick_start/pricing/",
    }


def parse_usage(raw: dict[str, Any] | None, model: str) -> dict[str, Any]:
    values = raw or {}
    miss = values.get("prompt_cache_miss_tokens")
    hit = values.get("prompt_cache_hit_tokens")
    completion = values.get("completion_tokens")
    prompt = values.get("prompt_tokens")
    complete = all(isinstance(v, int) for v in (miss, hit, completion, prompt))
    equation_ok = complete and prompt == miss + hit
    usage_status = "COMPLETE" if complete and equation_ok else "INCOMPLETE"
    pricing = price_snapshot(model)
    estimated_cost = None
    total_tokens = None
    if usage_status == "COMPLETE":
        total_tokens = prompt + completion
        estimated_cost = (
            miss * pricing["cache_miss_input"]
            + hit * pricing["cache_hit_input"]
            + completion * pricing["output"]
        ) / 1_000_000
    return {
        "prompt_cache_miss_tokens": miss if isinstance(miss, int) else None,
        "prompt_cache_hit_tokens": hit if isinstance(hit, int) else None,
        "completion_tokens": completion if isinstance(completion, int) else None,
        "total_tokens": total_tokens,
        "usage_status": usage_status,
        "price_snapshot": pricing,
        "estimated_cost": estimated_cost,
    }


def request_body(messages: list[dict[str, str]], stream: bool) -> dict[str, Any]:
    return {
        "model": settings.default_model,
        "messages": messages,
        "thinking": {"type": "enabled"},
        "reasoning_effort": settings.thinking_effort,
        "max_tokens": 700,
        "stream": stream,
        **({"stream_options": {"include_usage": True}} if stream else {}),
    }


def build_snap(
    *,
    started_at: str,
    started_clock: float,
    usage: dict[str, Any] | None,
    provider_request_id: str | None,
    status: str = "SUCCEEDED",
    error_code: str | None = None,
) -> dict[str, Any]:
    parsed = parse_usage(usage, settings.default_model)
    return {
        "cloud_call_id": new_id("call"),
        "provider": "deepseek",
        "model": settings.default_model,
        "request_started_at": started_at,
        "response_finished_at": iso_now(),
        "latency_ms": round((time.perf_counter() - started_clock) * 1000),
        "status": status,
        "provider_request_id": provider_request_id,
        "error_code": error_code,
        **parsed,
    }


class DeepSeekAdapter:
    def __init__(self) -> None:
        settings.validate_model_policy()
        if not settings.deepseek_api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not configured")
        self.url = settings.deepseek_base_url.rstrip("/") + "/chat/completions"
        self.headers = {
            "Authorization": f"Bearer {settings.deepseek_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, messages: list[dict[str, str]], stream: bool):
        payload = json.dumps(
            request_body(messages, stream=stream), ensure_ascii=False
        ).encode("utf-8")
        return urllib.request.Request(
            self.url,
            data=payload,
            headers=self.headers,
            method="POST",
        )

    def complete(self, messages: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
        started_at = iso_now()
        started_clock = time.perf_counter()
        with urllib.request.urlopen(self._request(messages, stream=False), timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"].get("content") or ""
        snap = build_snap(
            started_at=started_at,
            started_clock=started_clock,
            usage=payload.get("usage"),
            provider_request_id=payload.get("id"),
        )
        return content, snap

    def stream(self, messages: list[dict[str, str]]) -> Iterator[dict[str, Any]]:
        started_at = iso_now()
        started_clock = time.perf_counter()
        usage: dict[str, Any] | None = None
        provider_request_id: str | None = None
        with urllib.request.urlopen(self._request(messages, stream=True), timeout=120) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                provider_request_id = provider_request_id or chunk.get("id")
                if chunk.get("usage") is not None:
                    usage = chunk["usage"]
                choices = chunk.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    # reasoning_content is deliberately ignored and never persisted.
                    content = delta.get("content")
                    if content:
                        yield {"kind": "delta", "content": content}
        yield {
            "kind": "result",
            "snap": build_snap(
                started_at=started_at,
                started_clock=started_clock,
                usage=usage,
                provider_request_id=provider_request_id,
            ),
        }
