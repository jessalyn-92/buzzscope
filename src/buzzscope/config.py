"""Settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny .env loader so we don't need python-dotenv. Existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    openai_api_key: str | None
    openai_model: str
    db_path: Path
    synthetic_dir: Path
    ptt_delay_sec: float
    ptt_max_pages: int
    anonymize_salt: str
    agent_max_steps: int

    @property
    def has_llm(self) -> bool:
        return bool(self.openai_api_key)


def get_settings() -> Settings:
    _load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5-mini"),
        db_path=Path(os.getenv("BUZZSCOPE_DB", "data/buzzscope.db")),
        synthetic_dir=Path(os.getenv("BUZZSCOPE_SYNTHETIC_DIR", "data/synthetic")),
        ptt_delay_sec=float(os.getenv("PTT_DELAY_SEC", "1.0")),
        ptt_max_pages=int(os.getenv("PTT_MAX_PAGES", "20")),
        anonymize_salt=os.getenv("BUZZSCOPE_SALT", "buzzscope"),
        agent_max_steps=int(os.getenv("AGENT_MAX_STEPS", "24")),
    )
