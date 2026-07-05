"""Tests for LLMSchemaInterpreter."""

from __future__ import annotations

from opti_mind.data.llm_interpreter import LLMSchemaInterpreter
from opti_mind.data.models import CanonicalRole, ColumnProfile, DataProfileReport, FieldSemantics


def _make_interpreter(content: str) -> LLMSchemaInterpreter:
    from tests.conftest import FakeLLMClient

    return LLMSchemaInterpreter(llm_client=FakeLLMClient(content))


def _make_profile(column: str = "cost") -> DataProfileReport:
    return DataProfileReport(
        n_rows=1,
        n_cols=1,
        columns=[
            ColumnProfile(
                name=column,
                dtype="float64",
                missing_rate=0.0,
                non_null_count=1,
                unique_count=1,
                cardinality=1.0,
            )
        ],
    )


def test_llm_interpreter_returns_fields():
    """Interpret should return the fields produced by the LLM client."""
    response = (
        '{"fields": [{"column": "cost", "semantic_role": "cost", '
        '"optimization_symbol": "c_ij", "confidence": 1.0}], '
        '"reasoning": "cost is a cost parameter"}'
    )
    interpreter = _make_interpreter(response)
    expected = [
        FieldSemantics(
            column="cost",
            semantic_role="cost",
            optimization_symbol="c_ij",
            confidence=1.0,
        )
    ]

    result = interpreter.interpret(["cost"], _make_profile())
    assert result == expected


def test_interpret_falls_back_to_heuristic_on_bad_json():
    """A malformed LLM response must fall back to the heuristic interpreter."""
    interpreter = _make_interpreter("not valid json")
    result = interpreter.interpret(["demand"], _make_profile("demand"))
    assert len(result) == 1
    assert result[0].column == "demand"
    assert result[0].semantic_role == "demand"
    assert result[0].optimization_symbol == "d_i"


def test_interpret_falls_back_on_llm_exception():
    """An LLM client exception must fall back to the heuristic interpreter."""

    class ExplodingClient:
        def chat(self, messages, **kwargs):
            raise RuntimeError("boom")

    interpreter = LLMSchemaInterpreter(llm_client=ExplodingClient())
    result = interpreter.interpret(["capacity"], _make_profile("capacity"))
    assert result[0].semantic_role == "capacity"
    assert result[0].optimization_symbol == "Q_j"


def test_check_clarification_missing_role():
    """A missing critical role should produce a ClarificationRequest."""
    interpreter = _make_interpreter('{"fields": []}')
    semantics = interpreter.interpret(["id"], _make_profile("id"))
    req = interpreter.check_clarification(["id"], semantics)
    assert req is not None
    assert req.station == "data_intelligence"
    assert "demand" in req.question.lower() or "capacity" in req.question.lower()
    # No candidate column should remain when only an index/id column exists.
    assert req.options == []


def test_check_clarification_problem_type_filters_options():
    """Missing required parameter should only offer plausible columns."""
    response = (
        '{"fields": ['
        '{"column": "客户", "semantic_role": "customer", '
        '"optimization_symbol": null, "confidence": 1.0, '
        '"canonical_role": "customer_key", "is_index": true}, '
        '{"column": "工厂", "semantic_role": "facility", '
        '"optimization_symbol": null, "confidence": 1.0, '
        '"canonical_role": "facility_key", "is_index": true}, '
        '{"column": "需求量", "semantic_role": "demand", '
        '"optimization_symbol": "d_i", "confidence": 1.0, '
        '"canonical_role": "demand", "is_index": false}, '
        '{"column": "产能", "semantic_role": "capacity", '
        '"optimization_symbol": "Q_j", "confidence": 1.0, '
        '"canonical_role": "capacity", "is_index": false}, '
        '{"column": "运输费用", "semantic_role": "cost", '
        '"optimization_symbol": "c_ij", "confidence": 1.0, '
        '"canonical_role": "cost", "is_index": false}'
        "]}"
    )
    interpreter = _make_interpreter(response)
    columns = ["客户", "工厂", "需求量", "产能", "运输费用"]
    semantics = interpreter.interpret(columns, _make_profile())
    req = interpreter.check_clarification(columns, semantics, problem_type="facility_location")
    assert req is not None
    assert req.station == "data_intelligence"
    assert req.expected_field == "f_j"
    # No column should be offered because none of them look like fixed_cost.
    assert req.options == []
    assert "固定成本" in req.question


def test_check_clarification_offers_matching_column():
    """If a column hints at the missing role, it should be offered."""
    response = (
        '{"fields": ['
        '{"column": "customer", "semantic_role": "customer", '
        '"optimization_symbol": null, "confidence": 1.0, '
        '"canonical_role": "customer_key", "is_index": true}, '
        '{"column": "facility", "semantic_role": "facility", '
        '"optimization_symbol": null, "confidence": 1.0, '
        '"canonical_role": "facility_key", "is_index": true}, '
        '{"column": "demand", "semantic_role": "demand", '
        '"optimization_symbol": "d_i", "confidence": 1.0, '
        '"canonical_role": "demand", "is_index": false}, '
        '{"column": "capacity", "semantic_role": "capacity", '
        '"optimization_symbol": "Q_j", "confidence": 1.0, '
        '"canonical_role": "capacity", "is_index": false}, '
        '{"column": "transport_cost", "semantic_role": "cost", '
        '"optimization_symbol": "c_ij", "confidence": 1.0, '
        '"canonical_role": "cost", "is_index": false}, '
        '{"column": "opening_cost", "semantic_role": null, '
        '"optimization_symbol": null, "confidence": 1.0, '
        '"canonical_role": null, "is_index": false}'
        "]}"
    )
    interpreter = _make_interpreter(response)
    columns = ["customer", "facility", "demand", "capacity", "transport_cost", "opening_cost"]
    semantics = interpreter.interpret(columns, _make_profile())
    req = interpreter.check_clarification(columns, semantics, problem_type="facility_location")
    assert req is not None
    assert req.expected_field == "f_j"
    assert len(req.options) == 1
    assert req.options[0].value == "opening_cost"


def test_check_clarification_low_confidence():
    """A low-confidence mapping should produce a ClarificationRequest."""
    response = (
        '{"fields": ['
        '{"column": "demand", "semantic_role": "demand", '
        '"optimization_symbol": "d_i", "confidence": 1.0}, '
        '{"column": "capacity", "semantic_role": "capacity", '
        '"optimization_symbol": "Q_j", "confidence": 1.0}, '
        '{"column": "cost", "semantic_role": "cost", '
        '"optimization_symbol": "c_ij", "confidence": 0.1}'
        "]}"
    )
    interpreter = _make_interpreter(response)
    columns = ["demand", "capacity", "cost"]
    semantics = interpreter.interpret(columns, _make_profile())
    req = interpreter.check_clarification(columns, semantics)
    assert req is not None
    assert req.context.get("target_symbol") == "c_ij"


def test_llm_returns_canonical_role_and_is_index():
    """LLM response with canonical_role and is_index should be parsed."""
    response = (
        '{"fields": ['
        '{"column": "customer", "semantic_role": "customer", '
        '"optimization_symbol": null, "confidence": 1.0, '
        '"canonical_role": "customer_key", "is_index": true}, '
        '{"column": "demand", "semantic_role": "demand", '
        '"optimization_symbol": "d_i", "confidence": 1.0, '
        '"canonical_role": "demand", "is_index": false}'
        "]}"
    )
    interpreter = _make_interpreter(response)
    result = interpreter.interpret(["customer", "demand"], _make_profile("customer"))
    assert len(result) == 2
    assert result[0].canonical_role == CanonicalRole.CUSTOMER_KEY
    assert result[0].is_index is True
    assert result[1].canonical_role == CanonicalRole.DEMAND
    assert result[1].is_index is False


def test_check_clarification_skips_auto_computed_m():
    """Auto-computed parameters like inventory big-M should not be asked."""
    interpreter = _make_interpreter('{"fields": []}')
    item_role = CanonicalRole.ITEM_KEY if hasattr(CanonicalRole, "ITEM_KEY") else None
    period_role = CanonicalRole.PERIOD_KEY if hasattr(CanonicalRole, "PERIOD_KEY") else None
    semantics = [
        FieldSemantics(
            column="item",
            semantic_role="item",
            optimization_symbol=None,
            confidence=1.0,
            canonical_role=item_role,
            is_index=True,
        ),
        FieldSemantics(
            column="period",
            semantic_role="period",
            optimization_symbol=None,
            confidence=1.0,
            canonical_role=period_role,
            is_index=True,
        ),
        FieldSemantics(
            column="demand",
            semantic_role="demand",
            optimization_symbol="d_it",
            confidence=1.0,
            canonical_role=CanonicalRole.DEMAND,
            is_index=False,
        ),
        FieldSemantics(
            column="holding_cost",
            semantic_role="holding_cost",
            optimization_symbol="h_i",
            confidence=1.0,
            canonical_role=CanonicalRole.HOLDING_COST,
            is_index=False,
        ),
        FieldSemantics(
            column="ordering_cost",
            semantic_role="ordering_cost",
            optimization_symbol="s_i",
            confidence=1.0,
            canonical_role=CanonicalRole.ORDERING_COST,
            is_index=False,
        ),
        FieldSemantics(
            column="purchase_cost",
            semantic_role="purchase_cost",
            optimization_symbol="c_i",
            confidence=1.0,
            canonical_role=CanonicalRole.PURCHASE_COST,
            is_index=False,
        ),
        FieldSemantics(
            column="initial_inventory",
            semantic_role="initial_inventory",
            optimization_symbol="I0_i",
            confidence=1.0,
            canonical_role=CanonicalRole.INITIAL_INVENTORY,
            is_index=False,
        ),
    ]
    # Some canonical roles above may not exist in older models; skip if so.
    semantics = [s for s in semantics if s.canonical_role is not None]
    req = interpreter.check_clarification(
        [s.column for s in semantics], semantics, problem_type="inventory"
    )
    assert req is None


def test_heuristic_fallback_fills_canonical_role_and_is_index():
    """Heuristic fallback should fill canonical_role and is_index."""
    interpreter = _make_interpreter("bad json")
    result = interpreter.interpret(["customer", "demand", "lat"], _make_profile("customer"))
    assert len(result) == 3
    assert result[0].canonical_role == CanonicalRole.CUSTOMER_KEY
    assert result[0].is_index is True
    assert result[1].canonical_role == CanonicalRole.DEMAND
    assert result[1].is_index is False
    assert result[2].canonical_role == CanonicalRole.OTHER
    assert result[2].is_index is False
