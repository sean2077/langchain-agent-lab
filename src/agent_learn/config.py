"""Environment-backed runtime configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    langsmith_project: str = "agent-learn-synthetic"

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", defaults.ollama_base_url),
            ollama_model=os.getenv("OLLAMA_MODEL", defaults.ollama_model),
            langsmith_project=os.getenv("LANGSMITH_PROJECT", defaults.langsmith_project),
        )
