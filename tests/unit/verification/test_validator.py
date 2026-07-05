"""Tests for ModelValidator."""

from opti_mind.modeling.generator import IRGenerator
from opti_mind.modeling.ir_models import (
    IRConstraint,
    IRExpression,
    IRExpressionTerm,
    IRModel,
    IRParameter,
    IRSet,
    IRVariable,
)
from opti_mind.verification.validator import ModelValidator


def _make_valid_facility_location_ir() -> IRModel:
    """Build a structurally valid facility_location IR for tests."""
    return IRModel(
        problem_type="facility_location",
        sense="minimize",
        sets=[IRSet(name="I"), IRSet(name="J")],
        parameters=[IRParameter(name="d_i", sets=["I"]), IRParameter(name="f_j", sets=["J"])],
        variables=[
            IRVariable(name="x_ij", sets=["I", "J"], domain="binary"),
            IRVariable(name="y_j", sets=["J"], domain="binary"),
        ],
        objective=IRExpression(
            kind="linear",
            terms=[IRExpressionTerm(coef="f_j", var="y_j", sum_sets=["J"])],
            raw_expr="sum_{j in J} f_j * y_j",
        ),
        constraints=[
            IRConstraint(
                name="assignment",
                expr="sum_{j in J} x_ij",
                sense="eq",
                rhs="1",
                scope="forall i in I",
            ),
            IRConstraint(
                name="linking",
                expr="x_ij",
                sense="le",
                rhs="y_j",
                scope="forall i in I, j in J",
            ),
        ],
    )


def test_valid_ir_passes_all_checks() -> None:
    """A well-formed facility_location IR passes every check."""
    ir = _make_valid_facility_location_ir()
    report = ModelValidator().validate(ir)
    assert report.passed
    assert len(report.results) == 4
    assert all(r.passed for r in report.results)


def test_missing_variables_fails_structure() -> None:
    """An IR with no variables fails the structural check."""
    ir = _make_valid_facility_location_ir()
    ir.variables = []
    report = ModelValidator().validate(ir)
    assert not report.passed
    struct = next(r for r in report.results if r.check_name == "structural")
    assert not struct.passed
    assert any("no variables" in d for d in struct.details)


def test_undefined_set_fails_index() -> None:
    """A variable referencing an undefined set fails the index check."""
    ir = _make_valid_facility_location_ir()
    ir.variables[0].sets = ["I", "Z"]
    report = ModelValidator().validate(ir)
    index = next(r for r in report.results if r.check_name == "index")
    assert not index.passed
    assert any("Z" in d for d in index.details)


def test_invalid_domain_fails_math() -> None:
    """A variable with an invalid domain fails the math check."""
    ir = _make_valid_facility_location_ir()
    ir.variables[0].domain = "bogus"
    report = ModelValidator().validate(ir)
    math = next(r for r in report.results if r.check_name == "mathematical")
    assert not math.passed
    assert any("domain" in d for d in math.details)


def test_bounds_inverted_fails_math() -> None:
    """Lower > upper bound fails the math check."""
    ir = _make_valid_facility_location_ir()
    ir.variables[0].lower = 10.0
    ir.variables[0].upper = 1.0
    report = ModelValidator().validate(ir)
    math = next(r for r in report.results if r.check_name == "mathematical")
    assert not math.passed
    assert any("bound" in d for d in math.details)


def test_invalid_constraint_sense_fails_math() -> None:
    """A constraint with an invalid sense fails math."""
    ir = _make_valid_facility_location_ir()
    ir.constraints[0].sense = "invalid"
    report = ModelValidator().validate(ir)
    math = next(r for r in report.results if r.check_name == "mathematical")
    assert not math.passed
    assert any("sense" in d for d in math.details)


def test_missing_assignment_constraint_fails_logic() -> None:
    """facility_location without an assignment constraint fails logic."""
    ir = _make_valid_facility_location_ir()
    ir.constraints[0].name = "something_else"
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert not logic.passed


def test_missing_opening_variable_fails_logic() -> None:
    """facility_location without y_j fails logic."""
    ir = _make_valid_facility_location_ir()
    ir.variables = [v for v in ir.variables if v.name != "y_j"]
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert not logic.passed
    assert any("y_j" in d for d in logic.details)


def test_validate_dict_works() -> None:
    """validate_dict accepts a plain dict IR."""
    ir = _make_valid_facility_location_ir()
    data = ir.model_dump()
    report = ModelValidator().validate_dict(data)
    assert report.passed


def test_generated_ir_from_pipeline_passes() -> None:
    """IR produced by the full pipeline passes verification."""
    from opti_mind.data.models import OptimizationInstance
    from opti_mind.knowledge.models import ProblemSpecification
    from opti_mind.knowledge.retriever import KnowledgeRetriever
    from opti_mind.ontology.models import ProblemType

    knowledge = KnowledgeRetriever().retrieve(
        ProblemSpecification(
            problem_type=ProblemType.FACILITY_LOCATION,
            available_fields=["demand", "fixed_cost", "transport_cost"],
        )
    )
    instance = OptimizationInstance(
        problem_type="facility_location",
        sets={"I": ["c1", "c2"], "J": ["f1", "f2"]},
        parameters={"d": {"c1": 10, "c2": 20}, "f": {"f1": 5, "f2": 8}},
        meta={"dataset_id": "test"},
    )
    ir = IRGenerator().generate(knowledge, instance)
    report = ModelValidator().validate(ir)
    assert report.passed, [r.details for r in report.failures]


# ---------------------------------------------------------------------------
# network_flow logic checks
# ---------------------------------------------------------------------------


def _make_valid_network_flow_ir() -> IRModel:
    """Build a structurally valid network_flow IR for tests."""
    return IRModel(
        problem_type="network_flow",
        sense="minimize",
        sets=[IRSet(name="A"), IRSet(name="V")],
        parameters=[IRParameter(name="c_ij", sets=["A"])],
        variables=[
            IRVariable(name="x_ij", sets=["A"], domain="continuous"),
        ],
        objective=IRExpression(
            kind="linear",
            terms=[IRExpressionTerm(coef="c_ij", var="x_ij", sum_sets=["A"])],
            raw_expr="sum_{(i,j) in A} c_ij * x_ij",
        ),
        constraints=[
            IRConstraint(
                name="capacity",
                expr="x_ij",
                sense="le",
                rhs="10",
                scope="forall (i,j) in A",
            ),
            IRConstraint(
                name="conservation",
                expr="sum_{j in V} x_ij",
                sense="eq",
                rhs="0",
                scope="forall i in V",
            ),
        ],
    )


def test_logic_network_flow_pass() -> None:
    """network_flow with capacity, conservation, x_ij passes logic."""
    ir = _make_valid_network_flow_ir()
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert logic.passed


def test_logic_network_flow_fail() -> None:
    """network_flow without conservation fails logic."""
    ir = _make_valid_network_flow_ir()
    ir.constraints[1].name = "flow_balance"
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert not logic.passed


# ---------------------------------------------------------------------------
# scheduling logic checks
# ---------------------------------------------------------------------------


def _make_valid_scheduling_ir() -> IRModel:
    """Build a structurally valid continuous-time scheduling IR for tests."""
    return IRModel(
        problem_type="scheduling",
        sense="minimize",
        sets=[IRSet(name="J"), IRSet(name="P")],
        parameters=[
            IRParameter(name="p_j", sets=["J"]),
            IRParameter(name="w_j", sets=["J"]),
            IRParameter(name="M"),
        ],
        variables=[
            IRVariable(name="S_j", sets=["J"], domain="continuous"),
            IRVariable(name="C_j", sets=["J"], domain="continuous"),
            IRVariable(name="y_jk", sets=["P"], domain="binary"),
        ],
        objective=IRExpression(
            kind="linear",
            terms=[IRExpressionTerm(coef="w_j", var="C_j", sum_sets=["J"])],
            raw_expr="sum_{j in J} w_j * C_j",
        ),
        constraints=[
            IRConstraint(
                name="completion",
                expr="C_j - S_j",
                sense="ge",
                rhs="p_j",
                scope="forall j in J",
            ),
            IRConstraint(
                name="disjunctive_j_before_k",
                expr="S_k - C_j - M * y_jk",
                sense="ge",
                rhs="-M",
                scope="forall (j,k) in P",
            ),
            IRConstraint(
                name="disjunctive_k_before_j",
                expr="S_j - C_k + M * y_jk",
                sense="ge",
                rhs="0",
                scope="forall (j,k) in P",
            ),
        ],
    )


def test_logic_scheduling_pass() -> None:
    """scheduling with completion, disjunctive, S_j, C_j, y_jk passes logic."""
    ir = _make_valid_scheduling_ir()
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert logic.passed


def test_logic_scheduling_fail() -> None:
    """scheduling without disjunctive constraints fails logic."""
    ir = _make_valid_scheduling_ir()
    ir.constraints[1].name = "sequencing"
    ir.constraints[2].name = "ordering"
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert not logic.passed


# ---------------------------------------------------------------------------
# inventory logic checks
# ---------------------------------------------------------------------------


def _make_valid_inventory_ir() -> IRModel:
    """Build a structurally valid inventory IR for tests."""
    return IRModel(
        problem_type="inventory",
        sense="minimize",
        sets=[IRSet(name="I"), IRSet(name="T")],
        parameters=[
            IRParameter(name="c_it", sets=["I", "T"]),
            IRParameter(name="h_it", sets=["I", "T"]),
        ],
        variables=[
            IRVariable(name="x_it", sets=["I", "T"], domain="continuous"),
            IRVariable(name="y_it", sets=["I", "T"], domain="binary"),
            IRVariable(name="I_it", sets=["I", "T"], domain="continuous"),
        ],
        objective=IRExpression(
            kind="linear",
            terms=[IRExpressionTerm(coef="c_it", var="x_it", sum_sets=["I", "T"])],
            raw_expr="sum_{i in I, t in T} c_it * x_it",
        ),
        constraints=[
            IRConstraint(
                name="balance",
                expr="I_it",
                sense="eq",
                rhs="0",
                scope="forall i in I, t in T",
            ),
            IRConstraint(
                name="linking",
                expr="x_it",
                sense="le",
                rhs="M",
                scope="forall i in I, t in T",
            ),
        ],
    )


def test_logic_inventory_pass() -> None:
    """inventory with balance, linking, x_it, y_it, I_it passes logic."""
    ir = _make_valid_inventory_ir()
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert logic.passed


def test_logic_inventory_fail() -> None:
    """inventory without linking fails logic."""
    ir = _make_valid_inventory_ir()
    ir.constraints[1].name = "coupling"
    report = ModelValidator().validate(ir)
    logic = next(r for r in report.results if r.check_name == "logic")
    assert not logic.passed
