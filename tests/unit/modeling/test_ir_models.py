"""Tests for IR data models."""

from opti_mind.modeling.ir_models import (
    SCHEMA_VERSION,
    IRConstraint,
    IRExpression,
    IRExpressionTerm,
    IRModel,
    IRParameter,
    IRSet,
    IRVariable,
)


def test_ir_set_creation() -> None:
    """IRSet with from_instance members."""
    s = IRSet(name="I", description="customers")
    assert s.name == "I"
    assert s.members == "from_instance"


def test_ir_set_explicit_members():
    """IRSet with explicit member list."""
    s = IRSet(name="J", description="facilities", members=[0, 1, 2])
    assert s.members == [0, 1, 2]


def test_ir_variable_binary():
    """IRVariable with binary domain."""
    v = IRVariable(name="x_ij", description="assignment", sets=["I", "J"], domain="binary")
    assert v.domain == "binary"
    assert v.sets == ["I", "J"]


def test_ir_variable_continuous():
    """IRVariable with continuous domain and bounds."""
    v = IRVariable(
        name="x_ij",
        description="flow",
        sets=["A"],
        domain="continuous",
        lower=0.0,
    )
    assert v.domain == "continuous"
    assert v.lower == 0.0


def test_ir_constraint_creation():
    """IRConstraint stores expr, scope, sense, rhs."""
    c = IRConstraint(
        name="assign_once",
        expr="sum_{j in J} x_ij",
        scope="forall i in I",
        sense="eq",
        rhs="1",
    )
    assert c.sense == "eq"
    assert c.rhs == "1"


def test_ir_model_dump_safe():
    """model_dump_safe includes schema_version."""
    model = IRModel(problem_type="facility_location")
    dumped = model.model_dump_safe()
    assert dumped["meta"]["schema_version"] == SCHEMA_VERSION


def test_ir_model_full():
    """IRModel with all components."""
    model = IRModel(
        problem_type="facility_location",
        sense="minimize",
        sets=[IRSet(name="I"), IRSet(name="J")],
        parameters=[IRParameter(name="d_i", sets=["I"])],
        variables=[IRVariable(name="x_ij", sets=["I", "J"], domain="binary")],
        objective=IRExpression(kind="linear", terms=[IRExpressionTerm(coef="c_ij", var="x_ij")]),
        constraints=[
            IRConstraint(name="assign", expr="sum x_ij", sense="eq", rhs="1"),
        ],
    )
    assert len(model.sets) == 2
    assert len(model.variables) == 1
    assert model.objective is not None
    assert len(model.constraints) == 1
