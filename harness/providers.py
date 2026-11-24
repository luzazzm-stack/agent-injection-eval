"""Load baseURL + apiKey for a provider at runtime.

Keys are read from a JSON file the user owns and are only passed to the
OpenAI client. They are never printed, logged or written anywhere.

Config shape (same as providers.example.json):
  {"provider": {"<name>": {"options": {"baseURL": "...", "apiKey": "..."}}}}
"""
import json
import os
from pathlib import Path

DEFAULT_CONFIG = Path(os.environ.get("EVAL_PROVIDERS", Path(__file__).resolve().parent.parent / "providers.json"))

# short name -> (provider name in the config, model id)
MODELS = {
    # first choice was gemini-3.5-flash, but its free daily quota (20 requests) ran out
    # during smoke tests, so the same provider's gemini-3.5-flash-lite is used instead
    "gemini": ("gemini-free", "gemini-3.5-flash-lite"),
    "gpt-oss": ("groq-free", "openai/gpt-oss-120b"),
    "nemotron": ("nvidia-free", "nvidia/nemotron-3.5-super-vl-120b-a12b"),
}


def load_provider(provider_name, config_path=None):
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    cfg = json.loads(path.read_text(encoding="utf-8"))
    opts = cfg["provider"][provider_name]["options"]
    return opts["baseURL"], opts["apiKey"]


def list_models(provider_name, config_path=None):
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return list(cfg["provider"][provider_name].get("models", {}).keys())
