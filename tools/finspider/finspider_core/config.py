"""Load and sanity-check config.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError

REQUIRED_SECTIONS = ["data", "cache", "screener", "resolver", "thresholds", "flags",
                     "profiles", "red_flags", "verdict", "report", "sector"]


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml is not valid YAML: {e}") from e

    missing = [s for s in REQUIRED_SECTIONS if s not in cfg]
    if missing:
        raise ConfigError(f"config.yaml is missing section(s): {', '.join(missing)}")
    cfg.setdefault("manual_inputs", {})
    cfg["manual_inputs"] = cfg["manual_inputs"] or {}

    for name, t in cfg["thresholds"].items():
        if not isinstance(t, dict) or "good" not in t or "bad" not in t:
            raise ConfigError(f"thresholds.{name} needs both 'good' and 'bad'")
        if t["good"] == t["bad"]:
            raise ConfigError(f"thresholds.{name}: 'good' and 'bad' must differ")

    for pname, cats in cfg["profiles"].items():
        for cname, c in cats.items():
            if "weight" not in c or "metrics" not in c:
                raise ConfigError(f"profiles.{pname}.{cname} needs 'weight' and 'metrics'")
            for m in c["metrics"]:
                if m not in cfg["thresholds"]:
                    raise ConfigError(f"profiles.{pname}.{cname}: metric '{m}' has no thresholds entry")

    v = cfg["verdict"]
    if not (v["strong_accumulate"] > v["accumulate"] > v["hold"]):
        raise ConfigError("verdict cut-offs must satisfy strong_accumulate > accumulate > hold")
    cfg["_base_dir"] = str(path.resolve().parent)
    return cfg
