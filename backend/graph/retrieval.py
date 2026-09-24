import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("retrieval")


class GraphRAGRetriever:
    def __init__(self, tg_connection=None, config=None):
        self.tg = tg_connection
        self.config = config

    def retrieve(self, subject_id: str, pattern: str = None, k: int = 5) -> Dict[str, Any]:
        if self.config and self.config.dry_run:
            return self._dry_run_retrieve(subject_id, pattern, k)

        graph_evidence = self._get_graph_evidence(subject_id, pattern)
        policy_clauses = self._get_policy_clauses(pattern)
        similar_cases = self._get_similar_cases(pattern, subject_id, k)

        return {
            "subject_id": subject_id,
            "graph_evidence": graph_evidence,
            "policy_clauses": policy_clauses,
            "similar_cases": similar_cases,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "summary": self._summarize(graph_evidence, policy_clauses, similar_cases)
        }

    def _get_graph_evidence(self, subject_id: str, pattern: str = None) -> List[Dict]:
        evidence = []
        if self.config and self.config.dry_run:
            return self._mock_graph_evidence(subject_id, pattern)

        if self.tg:
            try:
                result = self.tg.gsql(f"RUN QUERY get_neighbourhood(\"{subject_id}\", 3)")
                evidence.append({
                    "id": f"graph-evidence-{subject_id}",
                    "kind": "graph",
                    "label": f"Neighbourhood of {subject_id}",
                    "summary": f"K-hop neighbourhood retrieved for {subject_id}",
                    "source": "GSQL get_neighbourhood",
                    "nodes": [subject_id],
                    "edges": []
                })
            except Exception as e:
                logger.error("Graph query failed: %s", e)

        return evidence

    def _get_policy_clauses(self, pattern: str = None) -> List[Dict]:
        if self.config and self.config.dry_run:
            from fixtures.cases import load_policies
            return load_policies()
        return []

    def _get_similar_cases(self, pattern: str, subject_id: str, k: int) -> List[Dict]:
        if self.config and self.config.dry_run:
            return []
        if self.tg:
            try:
                result = self.tg.gsql(f"RUN QUERY prior_case_similarity(\"{pattern}\", {k})")
                return []
            except Exception as e:
                logger.error("Similar case query failed: %s", e)
        return []

    def _summarize(self, graph_evidence, policy_clauses, similar_cases) -> str:
        parts = []
        parts.append(f"Graph evidence: {len(graph_evidence)} items retrieved")
        parts.append(f"Policy clauses: {len(policy_clauses)} applicable")
        parts.append(f"Similar prior cases: {len(similar_cases)} found")
        return "; ".join(parts)

    def _dry_run_retrieve(self, subject_id, pattern, k):
        from fixtures.cases import load_investigation
        inv = load_investigation(subject_id)
        return {
            "subject_id": subject_id,
            "graph_evidence": inv.get("nodes", []) if inv else [],
            "policy_clauses": [],
            "similar_cases": inv.get("similar", []) if inv else [],
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "summary": f"Dry-run retrieval for {subject_id}"
        }

    def _mock_graph_evidence(self, subject_id, pattern):
        return [{
            "id": f"EV-{subject_id}-1",
            "kind": "graph",
            "label": f"Evidence for {subject_id}",
            "summary": f"Graph evidence retrieved for {subject_id}",
            "source": "GSQL mock",
            "nodes": [subject_id],
            "edges": []
        }]

    def get_grounded_context(self, subject_id: str, pattern: str = None) -> str:
        bundle = self.retrieve(subject_id, pattern)
        summary = bundle["summary"]
        return f"Grounded context for {subject_id}: {summary}. Evidence items: {len(bundle['graph_evidence'])}. Policy clauses: {len(bundle['policy_clauses'])}. Prior cases: {len(bundle['similar_cases'])}."