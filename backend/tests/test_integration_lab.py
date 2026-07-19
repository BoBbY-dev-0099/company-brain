from __future__ import annotations

import pytest

from backend.demo.integration_lab import fixture_guard_results


@pytest.mark.asyncio
async def test_northstar_lab_exercises_signature_replay_and_web_guards():
    checks = await fixture_guard_results(now_epoch=1_700_000_000)
    by_id = {item["id"]: item for item in checks}
    assert by_id["slack_signed_delivery"]["passed"] is True
    assert by_id["slack_replay_window"]["passed"] is True
    assert by_id["github_signature"]["passed"] is True
    assert by_id["web_private_network"]["passed"] is True

