import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from config import Config

logger = logging.getLogger("memory")


class CaseMemory:
    def __init__(self, tg_connection=None, config: Config = None):
        self.tg = tg_connection
        self.config = config or Config()
        self._memory_dir = Path(self.config.temp_dir) / "memory"
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    def write(self, case_id: str, data: Dict[str, Any]) -> str:
        memory_path = self._memory_dir / f"{case_id}.json"
        record = {
            "case_id": case_id,
            "written_at": datetime.now(timezone.utc).isoformat(),
            "subject_id": data.get("subjectId"),
            "pattern": data.get("pattern"),
            "risk": data.get("risk"),
            "confidence": data.get("confidence"),
            "recommendation": data.get("recommendation"),
            "approval_route": data.get("approvalRoute"),
            "outcome": data.get("outcome"),
            "evidence_ids": data.get("evidenceIds", []),
            "trace_id": data.get("trace_id"),
            "steps_count": len(data.get("steps", []))
        }

        with open(memory_path, "w") as f:
            json.dump(record, f, indent=2, default=str)

        if self.tg and not self.config.dry_run:
            self._write_to_graph(case_id, record)

        logger.info("Case memory written for %s", case_id)
        return str(memory_path)

    def _write_to_graph(self, case_id: str, record: Dict[str, Any]):
        try:
            self.tg.gsql(
                f'INSERT INTO Case VALUES ("{case_id}", "{record.get("case_id", "")}", '
                f'"{record.get("pattern", "")}", {record.get("risk", 0)}, '
                f'{record.get("confidence", 0)}, "closed")'
            )
        except Exception as e:
            logger.error("Failed to write case to graph: %s", e)

    def retrieve_similar(self, pattern: str, subject_id: str, k: int = 3) -> List[Dict[str, Any]]:
        similar_cases = []

        memory_dir = Path(self.config.temp_dir) / "memory"
        if memory_dir.exists():
            for f in memory_dir.glob("*.json"):
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                        if data.get("pattern") == pattern:
                            similarity = self._compute_similarity(subject_id, data.get("subject_id", ""))
                            similar_cases.append({
                                "caseId": data["case_id"],
                                "similarity": similarity,
                                "outcome": data.get("outcome", "inconclusive"),
                                "decision": data.get("recommendation", {}).get("action", "N/A"),
                                "analystNote": data.get("outcome", "")
                            })
                except Exception:
                    continue

        similar_cases.sort(key=lambda x: x["similarity"], reverse=True)
        return similar_cases[:k]

    def _compute_similarity(self, id1: str, id2: str) -> float:
        if not id1 or not id2:
            return 0.0
        if id1 == id2:
            return 1.0
        return 0.5

    def get_context_for_investigation(self, case_id: str, pattern: str, subject_id: str) -> Dict[str, Any]:
        similar = self.retrieve_similar(pattern, subject_id, k=3)
        return {
            "case_id": case_id,
            "similar_cases": similar,
            "prior_decisions": [s["decision"] for s in similar],
            "prior_outcomes": [s["outcome"] for s in similar],
            "context": f"Previous {len(similar)} similar cases found for pattern {pattern}"
        }