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

    def resolved_api_key(self) -> str:
        """Resolve api_key via env var override.

        If api_key starts with 'env:', read the named env var (e.g. 'env:GEMINI_API_KEY').
        Otherwise return the literal value. Also auto-picks GEMINI_API_KEY for gemini provider.
        """
        if self.api_key.startswith("env:"):
            var = self.api_key[4:].strip()
            return os.getenv(var, "")
        if self.provider == "gemini" and self.api_key in ("", "not-needed"):
            return os.getenv("GEMINI_API_KEY", "")
        return self.api_key


class MedLocalConfig(BaseModel):
    """Application configuration."""

    model_config = ConfigDict(frozen=True)

    llm: LLMConfig = Field(default_factory=LLMConfig)
    teacher_llm: LLMConfig | None = Field(
        default=None,
        description="LLM for card generation (offline, can be a large model). Falls back to llm.",
    )
    language: str = Field(
        default="auto",
        description="Response language. 'auto' = match question language. Otherwise ISO name: English, Spanish, French, Portuguese, Swahili, Hindi, Arabic, etc.",
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


def _load_dotenv() -> None:
    """Minimal .env loader: load cwd/.env into os.environ without overwriting."""
    path = Path.cwd() / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def load_config() -> MedLocalConfig:
    """Load config from ~/.medlocal/config.toml."""
    _load_dotenv()

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
