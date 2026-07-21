"""Environment-backed runtime configuration."""

from __future__ import annotations

import ipaddress
import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def _validate_local_ollama_base_url(value: str) -> str:
    base_url = value.strip()
    try:
        parsed = urlsplit(base_url)
        _ = parsed.port
    except ValueError as exc:
        raise ValueError("OLLAMA_BASE_URL must be a valid loopback HTTP(S) URL") from exc

    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("OLLAMA_BASE_URL must be a valid loopback HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("OLLAMA_BASE_URL must not contain credentials")
    if parsed.query or parsed.fragment:
        raise ValueError("OLLAMA_BASE_URL must not contain a query string or fragment")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname != "localhost":
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError as exc:
            raise ValueError("OLLAMA_BASE_URL must target a loopback address") from exc
        if not address.is_loopback:
            raise ValueError("OLLAMA_BASE_URL must target a loopback address")
    return base_url


def _validate_ollama_timeout_seconds(value: str) -> float:
    try:
        timeout_seconds = float(value)
    except ValueError as exc:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a positive finite number") from exc
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("OLLAMA_TIMEOUT_SECONDS must be a positive finite number")
    return timeout_seconds


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_timeout_seconds: float = 300.0
    langsmith_project: str = "agent-learn-synthetic"

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            ollama_base_url=_validate_local_ollama_base_url(
                os.getenv("OLLAMA_BASE_URL", defaults.ollama_base_url)
            ),
            ollama_model=os.getenv("OLLAMA_MODEL", defaults.ollama_model),
            ollama_timeout_seconds=_validate_ollama_timeout_seconds(
                os.getenv("OLLAMA_TIMEOUT_SECONDS", str(defaults.ollama_timeout_seconds))
            ),
            langsmith_project=os.getenv("LANGSMITH_PROJECT", defaults.langsmith_project),
        )
