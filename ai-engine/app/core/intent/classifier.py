"""
Intent Classifier — Phase 3

Matches user messages to capability rules using keyword matching.
Future: upgrade to vector similarity (trigger_embedding) for semantic matching.
"""
import re
from app.db import crud


class IntentClassifier:
    """Classify user intent by matching against capability rules."""

    def classify(self, message: str, project_id: str) -> dict:
        """
        Classify a user message against the project's capability rules.

        Returns:
            {
                "type": "capability_rule" | "general",
                "rule": <rule dict> | None,
                "confidence": float (0-1),
                "matched_keywords": list[str]
            }
        """
        rules = crud.list_capability_rules(project_id)
        if not rules:
            return {"type": "general", "rule": None, "confidence": 0, "matched_keywords": []}

        msg_lower = message.lower().strip()
        best_match = None
        best_score = 0
        best_keywords = []

        for rule in rules:
            score, matched = self._score_rule(msg_lower, rule)
            # Apply priority boost (higher priority rules get a small boost)
            score += rule.get("priority", 0) * 0.01
            if score > best_score:
                best_score = score
                best_match = rule
                best_keywords = matched

        # Threshold: need at least 0.3 confidence to trigger
        if best_match and best_score >= 0.3:
            return {
                "type": "capability_rule",
                "rule": best_match,
                "confidence": min(best_score, 1.0),
                "matched_keywords": best_keywords,
            }

        return {"type": "general", "rule": None, "confidence": 0, "matched_keywords": []}

    def _score_rule(self, message: str, rule: dict) -> tuple[float, list[str]]:
        """Score how well a message matches a capability rule."""
        score = 0.0
        matched_keywords = []

        # 1. Keyword matching (primary method)
        keywords = rule.get("trigger_keywords", []) or []
        if keywords:
            hit_count = 0
            for kw in keywords:
                kw_lower = kw.lower().strip()
                if kw_lower and kw_lower in message:
                    hit_count += 1
                    matched_keywords.append(kw)
            if keywords:
                keyword_ratio = hit_count / len(keywords)
                score += keyword_ratio * 0.7  # Keywords contribute up to 0.7

        # 2. Trigger description fuzzy match (secondary)
        trigger = (rule.get("trigger_description", "") or "").lower()
        if trigger:
            # Simple word overlap
            trigger_words = set(re.findall(r'\w+', trigger))
            msg_words = set(re.findall(r'\w+', message))
            if trigger_words:
                overlap = len(trigger_words & msg_words)
                desc_ratio = overlap / len(trigger_words)
                score += desc_ratio * 0.3  # Description contributes up to 0.3

        return score, matched_keywords

    def classify_batch(self, messages: list[str], project_id: str) -> list[dict]:
        """Classify multiple messages (for evaluation)."""
        return [self.classify(msg, project_id) for msg in messages]


intent_classifier = IntentClassifier()
