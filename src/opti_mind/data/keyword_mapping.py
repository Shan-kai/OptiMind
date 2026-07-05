"""Single source of truth for column keyword → optimization semantics.

The mapping lives in ``config/keyword_mapping.toml`` and is consumed by both
``schema.py`` (heuristic interpretation) and ``instance_builder.py``
(instance assembly). Keeping it in one place prevents the three copies that
previously drifted apart.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from opti_mind.data.models import CanonicalRole


class KeywordConfig(NamedTuple):
    """Configuration for one column keyword."""

    keyword: str
    semantic_role: str | None
    optimization_symbol: str | None
    canonical_role: CanonicalRole | None
    is_index: bool


@lru_cache(maxsize=1)
def _load_keyword_configs() -> dict[str, KeywordConfig]:
    """Load and cache the TOML keyword mapping."""
    # Project root is three levels above this file: src/opti_mind/data/.. → root.
    config_path = Path(__file__).resolve().parents[3] / "config" / "keyword_mapping.toml"
    with config_path.open("rb") as f:
        data = tomllib.load(f)

    configs: dict[str, KeywordConfig] = {}
    for keyword, entry in data.get("keywords", {}).items():
        canonical = entry.get("canonical_role")
        configs[keyword] = KeywordConfig(
            keyword=keyword,
            semantic_role=entry.get("semantic_role"),
            optimization_symbol=entry.get("optimization_symbol"),
            canonical_role=CanonicalRole(canonical) if canonical else None,
            is_index=entry.get("is_index", False),
        )
    return configs


def _get_config(keyword: str) -> KeywordConfig | None:
    """Return the configuration for a keyword (case-insensitive)."""
    configs = _load_keyword_configs()
    return configs.get(keyword.lower().strip())


def get_semantic_role_and_symbol(keyword: str) -> tuple[str | None, str | None]:
    """Return ``(semantic_role, optimization_symbol)`` for a column keyword."""
    cfg = _get_config(keyword)
    if cfg is None:
        return None, None
    return cfg.semantic_role, cfg.optimization_symbol


def get_canonical_role(keyword: str) -> CanonicalRole | None:
    """Return the canonical role for a column keyword."""
    cfg = _get_config(keyword)
    return cfg.canonical_role if cfg else None


def is_index_keyword(keyword: str) -> bool:
    """Return True if the keyword typically denotes an index column."""
    cfg = _get_config(keyword)
    return cfg.is_index if cfg else False


def get_index_keywords() -> set[str]:
    """Return all keywords that are marked as index columns."""
    return {cfg.keyword for cfg in _load_keyword_configs().values() if cfg.is_index}


def get_canonical_role_for_semantic_role(role: str) -> CanonicalRole | None:
    """Map a semantic role string to its canonical role.

    Multiple keywords may share the same semantic role; the canonical role is
    guaranteed to be consistent across them.
    """
    for cfg in _load_keyword_configs().values():
        if cfg.semantic_role == role and cfg.canonical_role is not None:
            return cfg.canonical_role
    return None
