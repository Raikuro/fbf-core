from typing import Protocol, TypeVar, Generic, Any, Optional
from decimal import Decimal
from dataclasses import dataclass

T = TypeVar("T")

@dataclass(frozen=True)
class EvaluationOutcome:
    success: bool
    provenance: dict[str, Any]

@dataclass(frozen=True)
class OptimizerOutcome:
    candidate_value: Optional[Decimal]
    provenance: dict[str, Any]
    diagnostic: str

class Evaluator(Protocol):
    def evaluate(self, candidate: Any) -> EvaluationOutcome:
        ...

class SWROptimizer:
    """
    Stateless analytical solver for finding safe withdrawal rates.
    """
    
    def optimize(
        self,
        evaluator: Evaluator,
        domain_min: Decimal,
        domain_max: Decimal,
        precision: Decimal = Decimal("0.0001")
    ) -> OptimizerOutcome:
        """
        Determines the maximum candidate value that satisfies the evaluator.
        """
        if domain_min > domain_max:
            raise ValueError(f"Invalid domain: domain_min ({domain_min}) > domain_max ({domain_max})")
        
        low = domain_min
        high = domain_max
        best_candidate: Optional[Decimal] = None
        best_provenance: dict[str, Any] = {}
        
        while (high - low) > precision:
            mid = (low + high) / Decimal("2")
            outcome = evaluator.evaluate(mid)
            
            if outcome.success:
                best_candidate = mid
                best_provenance = outcome.provenance
                low = mid
            else:
                high = mid
                
        if best_candidate is None:
            return OptimizerOutcome(None, {}, "No candidate satisfied success criteria.")
            
        return OptimizerOutcome(
            best_candidate, 
            best_provenance, 
            f"Successfully found SWR: {best_candidate}"
        )
