"""Rule profile loader for Nova Air.

Loads versioned JSON regulatory profiles into strongly typed RuleProfile models.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from backend.app.models.domain import RuleProfile

DEFAULT_PROFILES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "profiles"


def get_profile_path(profile_id: str, profiles_dir: Optional[Path] = None) -> Path:
    base_dir = profiles_dir or DEFAULT_PROFILES_DIR
    return base_dir / profile_id / "profile.json"


@lru_cache(maxsize=16)
def load_rule_profile(profile_id: str = "nova_air_demo_v1", profiles_dir: Optional[str] = None) -> RuleProfile:
    dir_path = Path(profiles_dir) if profiles_dir else DEFAULT_PROFILES_DIR
    profile_path = get_profile_path(profile_id, dir_path)

    if not profile_path.exists():
        raise FileNotFoundError(f"Rule profile '{profile_id}' not found at: {profile_path}")

    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return RuleProfile.model_validate(data)
