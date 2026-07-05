"""Tests for IRGenerator."""

import pytest

from opti_mind.data.models import OptimizationInstance
from opti_mind.knowledge.models import ProblemSpecification
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.modeling.generator import IRGenerator
from opti_mind.ontology.models import ProblemType


def _make_knowledge_and_instance(problem_type: ProblemType):
    """Helper: retrieve knowledge and fabricate an instance."""
    retriever = KnowledgeRetriever()
    spec = ProblemSpecification(
        problem_type=problem_type,
        available_fields=["demand", "fixed_cost", "transport_cost", "capacity"],
    )
    knowledge = retriever.retrieve(spec)
    instance = OptimizationInstance(
        problem_type=problem_type.value,
        sets={"I": ["c1", "c2", "c3"], "J": ["f1", "f2"]},
        parameters={
            "d": {"c1": 10, "c2": 20, "c3": 15},
            "Q": {"f1": 100, "f2": 120},
            "f": {"f1": 50, "f2": 60},
            "c": {
                "c1": {"f1": 3.0, "f2": 4.0},
                "c2": {"f1": 2.0, "f2": 5.0},
                "c3": {"f1": 1.0, "f2": 6.0},
            },
        },
        meta={"dataset_id": "test_ds"},
    )
    return knowledge, instance


def test_generate_facility_location_ir():
    """Generate IR from facility_location knowledge + instance."""
    knowledge, instance = _make_knowledge_and_instance(ProblemType.FACILITY_LOCATION)
    ir = IRGenerator().generate(knowledge, instance)

    assert ir.problem_type == "facility_location"
    assert ir.sense == "minimize"
    assert len(ir.sets) == 2  # I, J
    assert ir.sets[0].name == "I"
    assert ir.sets[0].members == ["c1", "c2", "c3"]
    assert len(ir.variables) == 2  # x_ij, y_j
    assert any(v.name == "x_ij" and v.domain == "binary" for v in ir.variables)
    assert any(v.name == "y_j" for v in ir.variables)
    assert len(ir.constraints) == 3  # assignment, linking, capacity
    assert ir.objective is not None
    assert ir.objective.kind == "linear"


def test_generate_assignment_ir():
    """Generate IR from assignment knowledge + instance."""
    knowledge, instance = _make_knowledge_and_instance(ProblemType.ASSIGNMENT)
    ir = IRGenerator().generate(knowledge, instance)

    assert ir.problem_type == "assignment"
    assert len(ir.variables) == 1  # x_ij
    assert len(ir.constraints) == 3  # two assignment constraints + min cardinality
    assert ir.objective is not None


def test_generate_knapsack_ir():
    """Generate IR from knapsack knowledge + instance."""
    knowledge, instance = _make_knowledge_and_instance(ProblemType.KNAPSACK)
    ir = IRGenerator().generate(knowledge, instance)

    assert ir.problem_type == "knapsack"
    assert len(ir.variables) == 1
    assert ir.sense == "maximize"


def test_generate_all_seven_problem_types():
    """IRGenerator works for all 7 problem types."""
    from opti_mind.ontology.repository import OntologyRepository

    repo = OntologyRepository()
    retriever = KnowledgeRetriever()
    gen = IRGenerator()
    for pt in repo.list_types():
        spec = ProblemSpecification(problem_type=pt, available_fields=[])
        knowledge = retriever.retrieve(spec)
        instance = OptimizationInstance(
            problem_type=pt.value,
            sets={},
            parameters={},
            meta={},
        )
        ir = gen.generate(knowledge, instance)
        assert ir.problem_type == pt.value
        assert len(ir.variables) > 0
        assert len(ir.constraints) > 0
        assert ir.objective is not None
        assert ir.meta["schema_version"] == "1.0"


def test_generate_from_state():
    """Generate IR from workflow state dict."""
    knowledge, instance = _make_knowledge_and_instance(ProblemType.FACILITY_LOCATION)
    state = {
        "knowledge_package": knowledge.model_dump(),
        "instance": instance.model_dump(),
    }
    ir = IRGenerator().generate_from_state(state)
    assert ir.problem_type == "facility_location"
    assert len(ir.sets) == 2


def test_generate_from_state_missing_data():
    """Generate from state raises on missing data."""
    with pytest.raises(ValueError, match="Missing"):
        IRGenerator().generate_from_state({})


def test_ir_json_serializable():
    """IR is JSON-serializable via model_dump_safe."""
    import json

    knowledge, instance = _make_knowledge_and_instance(ProblemType.FACILITY_LOCATION)
    ir = IRGenerator().generate(knowledge, instance)
    dumped = ir.model_dump_safe()
    json_str = json.dumps(dumped)
    restored = json.loads(json_str)
    assert restored["problem_type"] == "facility_location"
    assert restored["meta"]["schema_version"] == "1.0"
    assert len(restored["variables"]) == 2


def test_ir_has_traceability():
    """IRParameters carry source traceability info."""
    knowledge, instance = _make_knowledge_and_instance(ProblemType.FACILITY_LOCATION)
    instance.parameters["d"] = {"c1": 10}
    ir = IRGenerator().generate(knowledge, instance)
    d_param = next(p for p in ir.parameters if p.name == "d_i")
    assert d_param.source.startswith("instance:")


def test_ir_generates_latex():
    """IR expressions and constraints include a LaTeX rendering."""
    knowledge, instance = _make_knowledge_and_instance(ProblemType.FACILITY_LOCATION)
    ir = IRGenerator().generate(knowledge, instance)

    assert ir.objective is not None
    assert ir.objective.latex
    assert r"\sum" in ir.objective.latex
    assert r"\cdot" in ir.objective.latex
    assert "y_{j}" in ir.objective.latex or "y_j" in ir.objective.latex

    for constraint in ir.constraints:
        assert constraint.latex
        assert r"\forall" in constraint.latex
        assert r"\in" in constraint.latex
        assert r"\le" in constraint.latex or "=" in constraint.latex
