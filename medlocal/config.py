"""Configuration for MedLocal — LLM and knowledge base settings."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

_DEFAULT_CONFIG_DIR = Path.home() / ".medlocal"


class LLMConfig(BaseModel):
    """LLM provider configuration."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(default="openai", description="openai, ollama, gemini")
    model: str = Field(default="gemma-4-e4b-it")
    api_key: str = Field(default="not-needed")
    base_url: str = Field(default="http://localhost:1234/v1")
    temperature: float = Field(default=0.3)


class MedLocalConfig(BaseModel):
    """Application configuration."""

    model_config = ConfigDict(frozen=True)

    llm: LLMConfig = Field(default_factory=LLMConfig)
    teacher_llm: LLMConfig | None = Field(
        default=None,
        description="LLM for card generation (offline, can be a large model). Falls back to llm.",
    )
    core_db: str = Field(
        default=str(_DEFAULT_CONFIG_DIR / "core.db"),
        description="Path to core (read-only) vstash knowledge base",
    )
    local_db: str = Field(
        default=str(_DEFAULT_CONFIG_DIR / "local.db"),
        description="Path to local (editable) vstash knowledge base",
    )
    recall_db: str = Field(
        default=str(_DEFAULT_CONFIG_DIR / "training.db"),
        description="Path to FSRS training database",
    )

    def get_teacher_llm(self) -> LLMConfig:
        """Teacher LLM config — falls back to main llm if not set."""
        return self.teacher_llm or self.llm


def load_config() -> MedLocalConfig:
    """Load config from ~/.medlocal/config.toml."""
    candidates = [
        Path.cwd() / "medlocal.toml",
        _DEFAULT_CONFIG_DIR / "config.toml",
    ]

    env_config = os.getenv("MEDLOCAL_CONFIG")
    if env_config:
        candidates.insert(0, Path(env_config).expanduser())

    for path in candidates:
        if path.exists():
            with open(path, "rb") as f:
                raw = tomllib.load(f)
            return MedLocalConfig.model_validate(raw)

    return MedLocalConfig()
