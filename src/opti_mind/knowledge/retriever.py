"""Knowledge retriever: queries ontology and builds knowledge packages."""

from __future__ import annotations

import difflib

from opti_mind.config import get_settings
from opti_mind.knowledge.models import KnowledgePackage, ProblemSpecification
from opti_mind.ontology.models import OntologyEntry
from opti_mind.ontology.repository import OntologyRepository

# Heuristic parameter-to-field matching rules.
# Keys are common substrings in ontology parameter names;
# values are common substrings in data field names.
_PARAMETER_FIELD_HINTS: dict[str, list[str]] = {
    "d_i": ["demand", "qty", "quantity", "requirement"],
    "f_j": ["fixed_cost", "fixed", "opening_cost"],
    "c_ij": ["transport_cost", "shipping_cost", "distance", "transport", "shipping", "cost"],
    "Q_j": ["capacity", "cap", "limit"],
    "s_i": ["supply", "stock", "available"],
    "d_j": ["demand", "need", "requirement"],
    "u_ij": ["capacity", "upper", "limit", "max"],
    "b_i": ["balance", "net", "flow"],
    "p_j": ["processing", "duration", "time"],
    "w_j": ["weight", "priority", "importance"],
    "K_i": ["fixed", "ordering", "setup"],
    "h_i": ["holding", "storage", "carrying"],
    "v_i": ["value", "profit", "benefit"],
    "w_i": ["weight", "mass", "size"],
}

# Substrings that disqualify a field from matching a parameter.
# For example, "fixed_cost" contains "cost" but should never be c_ij.
_PARAMETER_EXCLUDES: dict[str, list[str]] = {
    "c_ij": ["fixed"],
    "f_j": ["transport", "shipping"],
}


class KnowledgeRetriever:
    """Retrieves optimization knowledge from the ontology.

    Given a ProblemSpecification, looks up the matching OntologyEntry and
    builds a KnowledgePackage with matched data fields.
    """

    def __init__(
        self, repository: OntologyRepository | None = None, threshold: float | None = None
    ) -> None:
        self._repository = repository or OntologyRepository()
        self._threshold = (
            threshold if threshold is not None else get_settings().knowledge_match_threshold
        )

    def retrieve(self, spec: ProblemSpecification) -> KnowledgePackage:
        """Retrieve a knowledge package for the given problem specification.

        Args:
            spec: Problem specification describing the optimization task.

        Returns:
            KnowledgePackage with ontology entry and field mappings.

        Raises:
            KeyError: If the problem type is not in the ontology.

        """
        entry = self._repository.get(spec.problem_type)
        matched_fields = self._match_fields(entry, spec.available_fields)
        notes = self._generate_notes(entry, spec, matched_fields)
        confidence = self._compute_confidence(entry, spec, matched_fields)

        return KnowledgePackage(
            problem_type=spec.problem_type,
            ontology_entry=entry,
            variables=list(entry.variables),
            constraints=list(entry.constraints),
            objective=entry.objective,
            matched_fields=matched_fields,
            confidence=confidence,
            notes=notes,
        )

    def _match_fields(self, entry: OntologyEntry, available_fields: list[str]) -> dict[str, str]:
        """Match ontology parameters to available data fields.

        Uses substring matching first, then fuzzy matching via
        ``difflib.SequenceMatcher`` for remaining unmatched parameters.
        """
        matched: dict[str, str] = {}
        fields_lower = [f.lower() for f in available_fields]
        matched_field_names: set[str] = set()

        # Phase 1: substring matching
        for param_name in entry.parameters:
            hints = _PARAMETER_FIELD_HINTS.get(param_name, [])
            excludes = _PARAMETER_EXCLUDES.get(param_name, [])
            for hint in hints:
                for field_name, field_lower in zip(available_fields, fields_lower, strict=False):
                    if param_name in matched:
                        break
                    if field_name in matched_field_names:
                        continue
                    if any(exc in field_lower for exc in excludes):
                        continue
                    if hint in field_lower:
                        matched[param_name] = field_name
                        matched_field_names.add(field_name)
                        break
                if param_name in matched:
                    break

        # Phase 2: fuzzy matching for remaining unmatched parameters
        for param_name in entry.parameters:
            if param_name in matched:
                continue
            hints = _PARAMETER_FIELD_HINTS.get(param_name, [])
            excludes = _PARAMETER_EXCLUDES.get(param_name, [])
            for hint in hints:
                for field_name, field_lower in zip(available_fields, fields_lower, strict=False):
                    if param_name in matched:
                        break
                    if field_name in matched_field_names:
                        continue
                    if any(exc in field_lower for exc in excludes):
                        continue
                    ratio = difflib.SequenceMatcher(None, hint, field_lower).ratio()
                    if ratio >= self._threshold:
                        matched[param_name] = field_name
                        matched_field_names.add(field_name)
                        break
                if param_name in matched:
                    break

        # Phase 3: exact match on parameter name
        for param_name in entry.parameters:
            if param_name not in matched:
                for field_name in available_fields:
                    if field_name.lower() == param_name.lower():
                        matched[param_name] = field_name
                        break

        return matched

    def _generate_notes(
        self,
        entry: OntologyEntry,
        spec: ProblemSpecification,
        matched_fields: dict[str, str],
    ) -> list[str]:
        """Generate retrieval notes and warnings."""
        notes: list[str] = []
        unmatched_params = set(entry.parameters.keys()) - set(matched_fields.keys())
        if unmatched_params:
            notes.append(
                f"Unmatched parameters: {', '.join(sorted(unmatched_params))}. "
                "Model generation may need default values or user input."
            )
        if spec.constraints_hint:
            ontology_constraint_names = {c.name for c in entry.constraints}
            for hint in spec.constraints_hint:
                if hint.lower() not in [n.lower() for n in ontology_constraint_names]:
                    notes.append(
                        f"Constraint hint '{hint}' not directly matched to "
                        "ontology template. May need custom modeling."
                    )
        return notes

    def _compute_confidence(
        self,
        entry: OntologyEntry,
        spec: ProblemSpecification,
        matched_fields: dict[str, str],
    ) -> float:
        """Compute a confidence score for the retrieval."""
        if not entry.parameters:
            return 1.0
        match_ratio = len(matched_fields) / len(entry.parameters)
        # Base confidence from field matching
        confidence = 0.5 + 0.5 * match_ratio
        # Boost if business context is provided
        if spec.business_context:
            confidence = min(1.0, confidence + 0.05)
        return round(confidence, 3)
