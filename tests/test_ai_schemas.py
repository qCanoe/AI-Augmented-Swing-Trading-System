from ai_trading.ai.schemas import LLMDecision


def test_llm_decision_parse_valid_json() -> None:
    raw = """
    {
      "decision": "ALLOW",
      "confidence": 0.72,
      "risk_flags": ["VOLATILE"],
      "key_reasons": ["trend remains intact"]
    }
    """
    decision = LLMDecision.parse_response_text(raw)
    assert decision.decision == "ALLOW"
    assert decision.confidence == 0.72


def test_llm_decision_parse_invalid_payload_maps_to_deny() -> None:
    raw = '{"decision":"ALLOW","confidence":"bad","risk_flags":[],"key_reasons":[]}'
    decision = LLMDecision.parse_response_text(raw)
    assert decision.decision == "DENY"
    assert "INVALID_RESPONSE" in decision.risk_flags


def test_llm_decision_non_json_maps_to_deny() -> None:
    decision = LLMDecision.parse_response_text("hello world")
    assert decision.decision == "DENY"
