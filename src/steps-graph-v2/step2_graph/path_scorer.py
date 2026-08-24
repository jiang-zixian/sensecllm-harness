from __future__ import annotations

from .constants import STATUS_TRUE, STATUS_UNKNOWN
from .models import GraphEdge, SearchState


class PathScorer:
    def score(self, state: SearchState, edge: GraphEdge) -> float:
        score = state.path_score
        if edge.mechanism_name:
            score += 3.0
        if edge.final_status == STATUS_TRUE:
            score += 1.0
        if edge.final_status == STATUS_UNKNOWN:
            score -= 0.5
        if edge.relation_type == "observe":
            score += 2.0
        return score

