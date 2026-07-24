from decimal import Decimal
import pytest
from src.research.optimization.swr_optimizer import SWROptimizer, Evaluator, EvaluationOutcome

class MockEvaluator:
    def __init__(self, threshold: Decimal):
        self.threshold = threshold

    def evaluate(self, candidate: Decimal) -> EvaluationOutcome:
        # Success if candidate <= threshold
        return EvaluationOutcome(success=candidate <= self.threshold, provenance={"id": "mock"})

def test_swr_optimizer_finds_correct_rate():
    optimizer = SWROptimizer()
    threshold = Decimal("0.04")
    evaluator = MockEvaluator(threshold)
    
    result = optimizer.optimize(
        evaluator=evaluator,
        domain_min=Decimal("0.0"),
        domain_max=Decimal("0.1")
    )
    
    assert result.candidate_value is not None
    assert abs(result.candidate_value - threshold) < Decimal("0.0002")
    assert result.provenance == {"id": "mock"}

def test_swr_optimizer_returns_none_if_no_success():
    optimizer = SWROptimizer()
    # threshold is 0.0, everything above 0.0 fails
    evaluator = MockEvaluator(Decimal("-0.01"))
    
    result = optimizer.optimize(
        evaluator=evaluator,
        domain_min=Decimal("0.0"),
        domain_max=Decimal("0.1")
    )
    
    assert result.candidate_value is None
    assert "No candidate" in result.diagnostic

def test_swr_optimizer_validation_error():
    optimizer = SWROptimizer()
    evaluator = MockEvaluator(Decimal("0.0"))
    
    with pytest.raises(ValueError, match="Invalid domain"):
        optimizer.optimize(
            evaluator=evaluator,
            domain_min=Decimal("0.1"),
            domain_max=Decimal("0.0")
        )
