"""
Engine output rules baked into the report-writer system prompts (§2 Gold flag,
§5 COUNTERS + confidence honesty, §10 three-question self-check). Guards against
accidental removal.
"""
import pytest

from backend.services.report_writer import SYSTEM_PROMPT_FOOTBALL, SYSTEM_PROMPT_BASKETBALL


@pytest.mark.parametrize("prompt", [SYSTEM_PROMPT_FOOTBALL, SYSTEM_PROMPT_BASKETBALL])
def test_prompt_carries_engine_output_rules(prompt):
    assert "⚡" in prompt and "70%+" in prompt          # §2 Gold tendency flag
    assert "COUNTERS" in prompt                          # §5 surface contradictions
    assert "directional" in prompt                       # §5 low-confidence honesty
    # §10 three-question self-check
    assert "Who do we stop" in prompt
    assert "What will they do" in prompt
    assert "How do we beat them" in prompt


def test_no_invented_numbers_rule_still_present():
    # The pre-existing anti-fabrication rule must survive alongside the new ones.
    for p in (SYSTEM_PROMPT_FOOTBALL, SYSTEM_PROMPT_BASKETBALL):
        assert "no invented numbers" in p
