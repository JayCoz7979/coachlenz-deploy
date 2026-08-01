"""
Guard: minors' FILM cannot be imported/uploaded before the org makes the student-data
(COPPA/FERPA) authority attestation. Previously the attestation only gated roster
entry; film is the bigger surface (images to R2 + Anthropic, AI-extracted jersey
numbers = individual identifiers), so POST /games must 403 without it too.

Driven with asyncio.run + minimal stubs (no DB): the two entitlement guards no-op for
a paid org, so flow reaches the consent gate, which is the only query it runs.

Run:  python -m backend.tests.test_film_consent_gate
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.routers.games import create_game, GameCreate


class _ConsentDB:
    """The gate's only query is the LegalAcceptance count; return it as scalar_one()."""
    def __init__(self, consent_count: int):
        self._n = consent_count

    async def execute(self, *_a, **_k):
        return SimpleNamespace(scalar_one=lambda: self._n)


def _org():
    # Paid (non-trial) org: can_upload_game + assert_ready_to_analyze no-op, so flow
    # reaches the student-consent gate.
    return SimpleNamespace(id="org1", is_trial=False, trial_ends_at=None,
                           subscription_tier="starter", chosen_sports=["football"],
                           trial_games_used=0)


def _user():
    return SimpleNamespace(id="u1", organization_id="org1", email_verified=True)


def _body():
    return GameCreate(title="vs Rival", sport="football", file_name="game.mp4")


def test_upload_blocked_without_student_consent():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(create_game(body=_body(), user=_user(), org=_org(), db=_ConsentDB(0)))
    assert exc.value.status_code == 403
    d = exc.value.detail
    assert isinstance(d, dict) and d.get("code") == "student_consent_required", d


def run():
    test_upload_blocked_without_student_consent()
    print("FILM CONSENT GATE GUARD PASSED")


if __name__ == "__main__":
    run()
