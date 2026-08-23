"""Deterministic Upbit-compatible identifier generation."""

from hashlib import sha256
from uuid import UUID


class OrderIdentifierFactory:
    def __init__(self, namespace: str = "quantforge") -> None:
        normalized = namespace.strip().lower()
        if not normalized or len(normalized) > 12 or not normalized.replace("-", "").isalnum():
            raise ValueError("identifier namespace must be short alphanumeric text")
        self.namespace = normalized

    def create(self, *, intent_id: UUID, risk_decision_id: UUID) -> str:
        digest = sha256(f"{self.namespace}|{intent_id}|{risk_decision_id}".encode()).hexdigest()
        identifier = f"{self.namespace}-{digest[:48]}"
        if len(identifier) > 64:  # protected by namespace validation
            raise ValueError("generated identifier exceeds exchange limit")
        return identifier
