"""Tests for KnowledgeRetriever."""

from opti_mind.knowledge.models import ProblemSpecification
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.ontology.models import ProblemType
from opti_mind.ontology.repository import OntologyRepository


def test_retrieve_facility_location() -> None:
    """Retriever returns knowledge package for facility_location."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["demand", "capacity", "fixed_cost", "transport_cost"],
    )
    pkg = retriever.retrieve(spec)
    assert pkg.problem_type == ProblemType.FACILITY_LOCATION
    assert pkg.ontology_entry.problem_type == ProblemType.FACILITY_LOCATION
    assert len(pkg.variables) == 2  # x_ij, y_j
    assert len(pkg.constraints) == 3  # assignment, linking, capacity
    assert pkg.objective is not None
    assert pkg.confidence > 0.0


def test_retrieve_assignment() -> None:
    """Retriever returns knowledge package for assignment."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.ASSIGNMENT,
        available_fields=["cost", "distance"],
    )
    pkg = retriever.retrieve(spec)
    assert pkg.problem_type == ProblemType.ASSIGNMENT
    assert len(pkg.variables) == 1  # x_ij
    assert len(pkg.constraints) == 2  # one_task_per_agent, one_agent_per_task


def test_retrieve_knapsack() -> None:
    """Retriever returns knowledge package for knapsack."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.KNAPSACK,
        available_fields=["value", "weight", "capacity"],
    )
    pkg = retriever.retrieve(spec)
    assert pkg.problem_type == ProblemType.KNAPSACK
    assert len(pkg.variables) == 1  # x_i
    assert len(pkg.constraints) == 1  # capacity


def test_field_matching() -> None:
    """Retriever matches ontology parameters to available fields."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["demand", "fixed_cost", "transport_cost", "capacity"],
    )
    pkg = retriever.retrieve(spec)
    # Should match d_i -> demand, f_j -> fixed_cost, c_ij -> transport_cost
    assert "d_i" in pkg.matched_fields
    assert pkg.matched_fields["d_i"] == "demand"
    assert "f_j" in pkg.matched_fields
    assert pkg.matched_fields["f_j"] == "fixed_cost"


def test_confidence_with_full_match() -> None:
    """Confidence is high when all parameters are matched."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["demand", "fixed_cost", "transport_cost"],
    )
    pkg = retriever.retrieve(spec)
    assert pkg.confidence >= 0.8


def test_confidence_with_partial_match() -> None:
    """Confidence is lower when some parameters are unmatched."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["demand"],  # Only one field
    )
    pkg = retriever.retrieve(spec)
    assert pkg.confidence < 1.0
    assert len(pkg.notes) > 0  # Should have notes about unmatched params


def test_unmatched_parameters_noted() -> None:
    """Retriever notes unmatched parameters."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=[],  # No fields
    )
    pkg = retriever.retrieve(spec)
    assert any("Unmatched parameters" in note for note in pkg.notes)


def test_retrieve_unknown_problem_type_raises() -> None:
    """Retriever raises KeyError for unknown problem type."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.SCHEDULING,
        available_fields=[],
    )
    # SCHEDULING is registered, so this should work
    pkg = retriever.retrieve(spec)
    assert pkg.problem_type == ProblemType.SCHEDULING


def test_retrieve_all_seven_problem_types() -> None:
    """Retriever can retrieve knowledge packages for all 7 problem types."""
    retriever = KnowledgeRetriever()
    repo = OntologyRepository()
    for problem_type in repo.list_types():
        spec = ProblemSpecification(
            problem_type=problem_type,
            available_fields=[],
        )
        pkg = retriever.retrieve(spec)
        assert pkg.problem_type == problem_type
        assert pkg.ontology_entry is not None
        assert len(pkg.variables) > 0
        assert len(pkg.constraints) > 0
        assert pkg.objective is not None


def test_fuzzy_match_transport_cost() -> None:
    """``transp_c`` should fuzzy-match to ``c_ij`` via ``transport`` hint."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.TRANSPORTATION,
        available_fields=["supply", "transp_c", "capacity"],
    )
    pkg = retriever.retrieve(spec)
    assert "c_ij" in pkg.matched_fields
    assert pkg.matched_fields["c_ij"] == "transp_c"


def test_fuzzy_match_demand_qty() -> None:
    """``qty`` should match to ``d_i`` (direct hint) or ``d_j``."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["qty"],
    )
    pkg = retriever.retrieve(spec)
    assert "d_i" in pkg.matched_fields
    assert pkg.matched_fields["d_i"] == "qty"


def test_fuzzy_match_below_threshold() -> None:
    """Field ``xyz`` should not match any parameter (similarity below threshold)."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["demand", "fixed_cost", "xyz", "capacity"],
    )
    pkg = retriever.retrieve(spec)
    assert "c_ij" not in pkg.matched_fields


def test_excludes_still_block_fuzzy() -> None:
    """``fixed_cost`` must not be matched to ``c_ij`` via fuzzy matching."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=ProblemType.FACILITY_LOCATION,
        available_fields=["fixed_cost", "capacity"],
    )
    pkg = retriever.retrieve(spec)
    assert "c_ij" not in pkg.matched_fields
