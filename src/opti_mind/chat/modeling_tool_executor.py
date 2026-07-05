"""Symbol canonicalization helper for the orchestrator.

The previous modeling agent tools have been unified into the orchestrator's
``submit_parameters`` tool. This module only keeps the canonicalization logic
needed to map short parameter aliases to their full symbols.
"""

from __future__ import annotations

from typing import Any

from opti_mind.data.models import OptimizationInstance


def canonicalize_symbol(symbol: str, state: dict[str, Any]) -> str:
    """Map a base parameter name (e.g. 'c') to its canonical symbol ('c_ij')."""
    if "_" in symbol:
        return symbol
    instance_data = state.get("instance")
    if not instance_data:
        return symbol
    try:
        instance = OptimizationInstance.model_validate(instance_data)
    except Exception:  # noqa: BLE001
        return symbol
    entry = instance.meta.get("ontology_entry")
    if not isinstance(entry, dict):
        return symbol
    aliases = entry.get("aliases") or {}
    for base, canonical_list in aliases.items():
        if base == symbol and canonical_list:
            return str(canonical_list[0])
    return symbol
