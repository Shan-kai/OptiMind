"""Tests for IR to docplex model compiler."""

from opti_mind.data.models import OptimizationInstance
from opti_mind.knowledge.models import ProblemSpecification
from opti_mind.knowledge.retriever import KnowledgeRetriever
from opti_mind.modeling.generator import IRGenerator
from opti_mind.ontology.models import ProblemType
from opti_mind.solver.compiler import IRToModelCompiler


def _make_ir(problem_type=ProblemType.FACILITY_LOCATION):
    knowledge = KnowledgeRetriever().retrieve(
        ProblemSpecification(
            problem_type=problem_type,
            available_fields=["demand", "fixed_cost", "transport_cost"],
        )
    )
    instance = OptimizationInstance(
        problem_type=problem_type.value,
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={
            "d": {"c1": 10, "c2": 20},
            "f": {"f1": 50, "f2": 80},
            "Q": {"f1": 100, "f2": 120},
            "c": {"c1": {"f1": 3.0, "f2": 4.0}, "c2": {"f1": 2.0, "f2": 5.0}},
        },
        meta={"dataset_id": "test"},
    )
    return IRGenerator().generate(knowledge, instance)


def test_compile_produces_model():
    """Compiler produces a docplex Model with variables."""
    ir = _make_ir()
    compiler = IRToModelCompiler()
    model, var_index = compiler.compile(ir)
    assert model is not None
    assert "x_ij" in var_index
    assert "y_j" in var_index
    # x_ij is indexed -> should be a dict of variables
    assert isinstance(var_index["x_ij"], dict)
    assert isinstance(var_index["y_j"], dict)
    assert len(var_index["x_ij"]) == 4  # 2 customers x 2 facilities
    assert len(var_index["y_j"]) == 2


def test_compile_all_problem_types():
    """Compiler works for all 7 problem types."""
    from opti_mind.ontology.repository import OntologyRepository

    repo = OntologyRepository()
    gen = IRGenerator()
    retriever = KnowledgeRetriever()
    compiler = IRToModelCompiler()
    for pt in repo.list_types():
        knowledge = retriever.retrieve(ProblemSpecification(problem_type=pt, available_fields=[]))
        instance = OptimizationInstance(
            problem_type=pt.value,
            sets={"I": [0, 1], "J": [0, 1], "T": [0, 1]},
            parameters={},
            meta={},
        )
        ir = gen.generate(knowledge, instance)
        model, var_index = compiler.compile(ir)
        assert model is not None
        assert len(var_index) > 0
