from __future__ import annotations

import datetime as dt
import tomllib
from pathlib import Path
from zoneinfo import ZoneInfo


def load_config(path: Path) -> dict:
    with path.open("rb") as handle:
        config = tomllib.load(handle)
    end_date = config["run"]["end_date"]
    if end_date == "auto":
        config["run"]["end_date"] = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    return config

