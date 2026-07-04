"""Tests for the brain_cache frozen prefix builder."""

from __future__ import annotations

from backend.core.brain_cache import build_frozen_prefix
from backend.core.schema import CompanyBrainSkill, SkillPattern


def _mini_skill(skill_id: str) -> CompanyBrainSkill:
    return CompanyBrainSkill(
        skill_id=skill_id,
        name=f"Skill {skill_id}",
        domain="engineering",
        summary="A test skill.",
        pattern=SkillPattern(keywords=["k1", "k2"]),
    )


def test_frozen_prefix_handles_empty_brain():
    prefix = build_frozen_prefix([])
    # Rough heuristic: >1024 tokens means >~3000 characters of plain English.
    assert len(prefix) > 3000
    assert "(brain is currently empty" in prefix


def test_frozen_prefix_is_stable_for_same_skills():
    skills = [_mini_skill(f"s-{i}") for i in range(5)]
    a = build_frozen_prefix(skills)
    b = build_frozen_prefix(skills)
    assert a == b  # stability matters for prefix cache


def test_frozen_prefix_sorts_skills_deterministically():
    skills = [_mini_skill("z"), _mini_skill("a"), _mini_skill("m")]
    prefix = build_frozen_prefix(skills)
    # All three names should appear and the order in text should match sorted ids.
    a_pos = prefix.index("Skill a")
    m_pos = prefix.index("Skill m")
    z_pos = prefix.index("Skill z")
    assert a_pos < m_pos < z_pos


def test_frozen_prefix_caps_at_20_skills():
    skills = [_mini_skill(f"s-{i:03d}") for i in range(50)]
    prefix = build_frozen_prefix(skills)
    # The 21st-and-beyond skill names should not appear.
    assert "Skill s-020" not in prefix
    assert "Skill s-019" in prefix


def test_compiler_system_message_uses_explicit_cache():
    from backend.core.compiler import _compiler_system_message

    msg = _compiler_system_message("frozen prefix text")
    assert msg["role"] == "system"
    assert isinstance(msg["content"], list)
    assert msg["content"][0]["cache_control"] == {"type": "ephemeral"}
