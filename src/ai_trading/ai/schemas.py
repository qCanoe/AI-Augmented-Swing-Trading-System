"""AI input/output schemas and strict parsing helpers."""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class MarketSnapshot(BaseModel):
    """Normalized market snapshot for LLM gating."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[A-Z0-9]+$")
    trend: Literal["UP", "DOWN", "NEUTRAL"]
    atr_quantile: float = Field(ge=0.0, le=1.0)
    atr_label: Literal["LOW", "NORMAL", "HIGH"]
    funding_rate: float | None = None
    funding_available: bool
    open_interest: float | None = None
    open_interest_available: bool
    event_risk: Literal["YES", "NO"] = "NO"
    candidate_type: Literal["Trend Pullback"] = "Trend Pullback"
    position_side: Literal["LONG"] = "LONG"
    indicators: dict[str, float]


class LLMDecision(BaseModel):
    """Strict LLM decision schema."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["ALLOW", "DENY", "REDUCE"]
    confidence: float = Field(ge=0.0, le=1.0)
    risk_flags: list[str] = Field(default_factory=list)
    key_reasons: list[str] = Field(default_factory=list)

    @classmethod
    def deny_default(cls, reason: str) -> "LLMDecision":
        """Construct a conservative deny decision."""
        return cls(
            decision="DENY",
            confidence=0.0,
            risk_flags=["INVALID_RESPONSE"],
            key_reasons=[reason],
        )

    @classmethod
    def parse_strict(cls, payload: dict[str, Any]) -> "LLMDecision":
        """Parse a raw dict. Any violation is mapped to DENY."""
        try:
            return cls.model_validate(payload)
        except ValidationError as exc:
            return cls.deny_default(f"schema_validation_error: {exc.errors()[0]['msg']}")

    @classmethod
    def parse_response_text(cls, text: str) -> "LLMDecision":
        """Parse model text response. Non-JSON/invalid JSON is DENY."""
        try:
            json_obj = _extract_json_obj(text)
        except ValueError as exc:
            return cls.deny_default(str(exc))
        return cls.parse_strict(json_obj)


def _extract_json_obj(text: str) -> dict[str, Any]:
    """Extract the first JSON object from plain text or fenced content."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        decoded = json.loads(stripped)
        if isinstance(decoded, dict):
            return decoded
        raise ValueError("model_response_json_not_object")

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    if fenced_match:
        decoded = json.loads(fenced_match.group(1))
        if isinstance(decoded, dict):
            return decoded
        raise ValueError("model_response_json_not_object")

    brace_match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if brace_match:
        decoded = json.loads(brace_match.group(0))
        if isinstance(decoded, dict):
            return decoded
        raise ValueError("model_response_json_not_object")

    raise ValueError("model_response_not_json")
