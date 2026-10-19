"""Configuration: config.toml, overridden by .env / environment variables."""
import os
import tomllib
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
ROOT = SRC.parent


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def load(path: Path | None = None) -> dict:
    _load_dotenv(ROOT / ".env")
    cfg = tomllib.loads((path or SRC / "config.toml").read_text(encoding="utf-8"))
    llm = cfg["llm"]
    llm["model"] = os.environ.get("LLM_NAME", llm["model"])
    llm["base_url"] = os.environ.get("LLM_BASE_URL", llm["base_url"]).rstrip("/")
    llm["api_key"] = os.environ.get("LLM_API_KEY", "")
    cfg["paths"]["data_dir"] = (SRC / cfg["paths"]["data_dir"]).resolve()
    cfg["paths"]["site_dir"] = (SRC / cfg["paths"]["site_dir"]).resolve()
    cfg["paths"]["data_dir"].mkdir(parents=True, exist_ok=True)
    return cfg


def model_for(cfg: dict, feature: str) -> str:
    """Apertus model of one feature: env LLM_NAME_<FEATURE>, else [llm.models] in config.toml, else the default
    model (LLM_NAME / llm.model). The per-feature choice comes from the 70B vs 8B comparison (docs/model_comparison.md)."""
    return (os.environ.get(f"LLM_NAME_{feature.upper()}") or cfg["llm"].get("models", {}).get(feature)
            or cfg["llm"]["model"])
