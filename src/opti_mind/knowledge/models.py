"""Models for knowledge retrieval: backward-compatible aliases.

``ProblemSpecification`` and ``KnowledgePackage`` have moved to
``opti_mind.ontology.models``. This module re-exports them so existing imports
continue to work during the migration.
"""

from __future__ import annotations

from opti_mind.ontology.models import KnowledgePackage, ProblemSpecification

__all__ = ["KnowledgePackage", "ProblemSpecification"]
