import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger("policy")


class PolicyEngine:
    def __init__(self, policies: List[Dict] = None):
        self.policies = policies or self._default_policies()
        self._rules = self._build_rules()

    def _default_policies(self) -> List[Dict]:
        from fixtures.cases import load_policies
        return load_policies()

    def _build_rules(self) -> Dict[str, Dict]:
        rules = {}
        for p in self.policies:
            rules[p["id"]] = {
                "id": p["id"],
                "doc": p["doc"],
                "clause": p["clause"],
                "title": p["title"],
                "text": p["text"],
                "conditions": self._parse_conditions(p),
                "effects": self._parse_effects(p)
            }
        return rules

    def _parse_conditions(self, policy: Dict) -> Dict[str, Any]:
        text = policy["text"]
        conditions = {}
        if "0.70" in text:
            conditions["risk_threshold"] = 0.70
        if "0.40" in text:
            conditions["risk_threshold"] = 0.40
        if "0.75" in text:
            conditions["confidence_threshold"] = 0.75
        if "10 or more" in text:
            conditions["min_count"] = 10
        if "anonymizing" in text.lower():
            conditions["requires_anonymizer"] = True
        if "dual approval" in text.lower():
            conditions["requires_dual_approval"] = True
        return conditions

    def _parse_effects(self, policy: Dict) -> Dict[str, Any]:
        text = policy["text"]
        effects = {"allowed_actions": [], "approval_required": 1, "auto_executable": False}
        if "without analyst approval" in text:
            effects["auto_executable"] = True
            effects["approval_required"] = 0
        if "dual approval" in text.lower():
            effects["approval_required"] = 2
        if "may be blocked" in text.lower() or "may be frozen" in text.lower():
            effects["allowed_actions"].append("block")
        if "require step-up" in text.lower():
            effects["allowed_actions"].append("step_up")
        if "monitor" in text.lower():
            effects["allowed_actions"].append("monitor")
        if "recall" in text.lower():
            effects["allowed_actions"].append("recall")
        if "file" in text.lower() and "SAR" in text:
            effects["allowed_actions"].append("file_sar")
        return effects

    def lookup(self, doc: str = None, clause: str = None, facts: Dict = None) -> Dict[str, Any]:
        for p in self.policies:
            if doc and p["doc"] != doc:
                continue
            if clause and p["clause"] != clause:
                continue
            conditions = self._parse_conditions(p)
            effects = self._parse_effects(p)
            if facts:
                if not self._check_facts(conditions, facts):
                    continue
            return {
                "id": p["id"],
                "title": p["title"],
                "clause": p["clause"],
                "text": p["text"],
                "conditions": conditions,
                "effects": effects,
                "allowed": True
            }
        return {"allowed": False, "reason": f"No matching policy found for doc={doc}, clause={clause}"}

    def _check_facts(self, conditions: Dict, facts: Dict) -> bool:
        if "risk_threshold" in conditions and "risk" in facts:
            if facts["risk"] < conditions["risk_threshold"]:
                return False
        if "confidence_threshold" in conditions and "confidence" in facts:
            if facts["confidence"] < conditions["confidence_threshold"]:
                return False
        if "min_count" in conditions and "count" in facts:
            if facts["count"] < conditions["min_count"]:
                return False
        return True

    def check_action(
        self,
        action_id: str,
        pattern: str,
        risk: float,
        confidence: float,
        route: str,
        additional_facts: Dict = None
    ) -> Dict[str, Any]:
        facts = {"risk": risk, "confidence": confidence}
        if additional_facts:
            facts.update(additional_facts)

        relevant_policies = [p for p in self.policies if self._pattern_matches(p, pattern)]

        for p in relevant_policies:
            conditions = self._parse_conditions(p)
            effects = self._parse_effects(p)
            if not self._check_facts(conditions, facts):
                continue
            if action_id in effects.get("allowed_actions", []):
                return {
                    "allowed": True,
                    "policyId": p["id"],
                    "title": p["title"],
                    "clause": p["clause"],
                    "reason": f"Action permitted under {p['id']} §{p['clause']}"
                }

        blocking_clause = self._find_blocking_clause(pattern, risk, confidence, route)
        return {
            "allowed": False,
            "policyId": "",
            "reason": blocking_clause.get("reason", f"Action {action_id} not permitted for pattern {pattern} at risk {risk}")
        }

    def _pattern_matches(self, policy: Dict, pattern: str) -> bool:
        text = policy["text"].lower()
        pattern_map = {
            "card_testing": ["card", "authorization", "micro"],
            "mule_network": ["mule", "transfer", "ring"],
            "account_takeover": ["account", "device", "login", "password"],
            "app_scam": ["scam", "fraud", "push-payment", "payment", "safe account"],
            "synthetic_identity": ["identity", "applicant", "ssn", "thin-file"],
            "friendly_fraud": ["friendly", "chargeback", "dispute", "false positive"]
        }
        keywords = pattern_map.get(pattern, [])
        return any(kw in text for kw in keywords)

    def _find_blocking_clause(self, pattern, risk, confidence, route) -> Dict[str, str]:
        for p in self.policies:
            conditions = self._parse_conditions(p)
            if "risk_threshold" in conditions and risk < conditions["risk_threshold"]:
                return {"policyId": p["id"], "reason": f"Risk {risk:.2f} below threshold {conditions['risk_threshold']} in {p['id']} §{p['clause']}"}
            if "confidence_threshold" in conditions and confidence < conditions["confidence_threshold"]:
                return {"policyId": p["id"], "reason": f"Confidence {confidence:.2f} below threshold {conditions['confidence_threshold']} in {p['id']} §{p['clause']}"}
            if conditions.get("requires_dual_approval") and route != "dual_approval":
                return {"policyId": p["id"], "reason": f"{p['id']} requires dual approval, current route is {route}"}
        return {"policyId": "", "reason": "No matching policy clause found"}

    def determine_route(self, pattern: str, risk: float, confidence: float) -> Dict[str, Any]:
        if pattern == "card_testing":
            if risk >= 0.7:
                return {"route": "auto_execute", "policyId": "CARD-2.1.3", "approval_required": 0}
            return {"route": "analyst_approval", "policyId": "CARD-2.1.3", "approval_required": 1}
        elif pattern == "mule_network":
            if risk >= 0.7:
                return {"route": "dual_approval", "policyId": "AML-4.2.2", "approval_required": 2}
            return {"route": "analyst_approval", "policyId": "AML-4.2.2", "approval_required": 1}
        elif pattern == "app_scam":
            return {"route": "analyst_approval", "policyId": "APP-3.1.4", "approval_required": 1}
        elif pattern == "account_takeover":
            if risk >= 0.7 and confidence >= 0.75:
                return {"route": "dual_approval", "policyId": "ACC-1.4.3", "approval_required": 2}
            return {"route": "analyst_approval", "policyId": "ACC-1.4.1", "approval_required": 1}
        elif pattern == "synthetic_identity":
            return {"route": "analyst_approval", "policyId": "ACC-1.4.3", "approval_required": 1}
        elif pattern == "friendly_fraud":
            if risk < 0.4:
                return {"route": "auto_execute", "policyId": "GEN-0.2.4", "approval_required": 0}
            return {"route": "analyst_approval", "policyId": "GEN-0.2.4", "approval_required": 1}
        return {"route": "analyst_approval", "policyId": "GEN-0.2.1", "approval_required": 1}

    def requires_sar(self, pattern: str, risk: float, route: str) -> bool:
        return pattern in ("mule_network", "app_scam") and risk >= 0.5 and route != "auto_execute"