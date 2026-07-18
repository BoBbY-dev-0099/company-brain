from backend.core.sag_evaluator import SagRuleError, evaluate_rule, provenance_to_rule
from backend.core.schema import ApplicabilityCondition, ApplicabilityOperator


def test_and_operator_all_true():
    rule = {"and": [{"gte": ["export_chunk_size_mb", 10]}, {"eq": ["region", "us-east-1"]}]}
    out = evaluate_rule(rule, {"export_chunk_size_mb": 25, "region": "us-east-1"})
    assert out["result"] is True
    assert out["trace"]["node"] == "and"


def test_and_operator_one_false():
    rule = {"and": [{"gte": ["export_chunk_size_mb", 10]}, {"eq": ["region", "us-east-1"]}]}
    out = evaluate_rule(rule, {"export_chunk_size_mb": 8, "region": "us-east-1"})
    assert out["result"] is False


def test_or_operator_one_true():
    rule = {"or": [{"eq": ["region", "eu"]}, {"eq": ["region", "us-east-1"]}]}
    out = evaluate_rule(rule, {"region": "us-east-1"})
    assert out["result"] is True


def test_numeric_comparison():
    assert evaluate_rule({"gt": ["n", 10]}, {"n": 11})["result"] is True
    assert evaluate_rule({"lte": ["n", 10]}, {"n": 10})["result"] is True


def test_regex_match():
    out = evaluate_rule({"regex": ["version", r"^2\."]}, {"version": "2.1.0"})
    assert out["result"] is True


def test_missing_field_returns_false():
    out = evaluate_rule({"gte": ["export_chunk_size_mb", 10]}, {})
    assert out["result"] is False
    assert out["trace"]["note"] == "MISSING_FIELD"


def test_nested_depth_exceeded():
    rule: dict = {"not": {"lit": True}}
    for _ in range(12):
        rule = {"not": rule}
    try:
        evaluate_rule(rule, {})
        assert False, "expected RULE_DEPTH_EXCEEDED"
    except SagRuleError as exc:
        assert exc.code == "RULE_DEPTH_EXCEEDED"


def test_benchmark_p99_under_10ms():
    rule = {
        "and": [
            {"gte": ["export_chunk_size_mb", 10]},
            {"eq": ["region", "us-east-1"]},
            {"regex": ["version", r"^2\."]},
        ]
    }
    samples = []
    for i in range(200):
        out = evaluate_rule(
            rule,
            {
                "export_chunk_size_mb": 8 if i % 2 == 0 else 25,
                "region": "us-east-1",
                "version": "2.0.0",
            },
        )
        samples.append(out["evaluated_in_ms"])
    samples.sort()
    p99 = samples[int(0.99 * (len(samples) - 1))]
    assert p99 < 10.0


def test_provenance_to_rule_demo_skill():
    applies = [
        ApplicabilityCondition(
            key="export_chunk_size_mb", operator=ApplicabilityOperator.gt, value=10
        )
    ]
    invalidated = [
        ApplicabilityCondition(
            key="export_chunk_size_mb", operator=ApplicabilityOperator.lte, value=10
        )
    ]
    rule = provenance_to_rule(applies, invalidated)
    assert evaluate_rule(rule, {"export_chunk_size_mb": 8})["result"] is False
    assert evaluate_rule(rule, {"export_chunk_size_mb": 25})["result"] is True
