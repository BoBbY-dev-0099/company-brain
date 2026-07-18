"""Tests for the immutable judge fixture versus mutable sandbox boundary."""

from __future__ import annotations

import pytest

from backend.config import settings
from backend.demo import state


def test_canonical_judge_fixture_is_not_mutable():
    assert state.is_canonical_demo_org(settings.JUDGE_DEMO_ORG_ID)
    with pytest.raises(ValueError, match="immutable"):
        state.assert_demo_org_mutable(settings.JUDGE_DEMO_ORG_ID)


def test_sandbox_is_explicitly_mutable_in_policy():
    assert state.is_sandbox_org(settings.SANDBOX_ORG_ID)
    state.assert_demo_org_mutable(settings.SANDBOX_ORG_ID)
    policy = state.demo_org_policy()
    assert policy["judge_demo"]["immutable"] is True
    assert policy["sandbox"]["immutable"] is False
