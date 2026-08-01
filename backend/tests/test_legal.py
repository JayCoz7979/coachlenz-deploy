"""
Unit tests for the legal/COPPA consent service (backend/services/legal.py). Uses a
minimal fake DB (no real database) to exercise the version map, the acceptance
lookup, and the student-data gate.
"""
import asyncio
from types import SimpleNamespace  # noqa: F401

import pytest
from fastapi import HTTPException

from backend.services.legal import (
    DOCUMENT_VERSIONS, STUDENT_DATA_ATTESTATION, RECONSENT_DOCUMENTS,
    has_current_acceptance, has_current_user_acceptance, user_reconsent_needed,
    assert_student_consent, record_acceptance,
)


class _Res:
    def __init__(self, v):
        self.v = v

    def scalar_one(self):
        return self.v


class _DB:
    def __init__(self, count):
        self.count = count
        self.added = []

    async def execute(self, *_a, **_k):
        return _Res(self.count)

    def add(self, obj):
        self.added.append(obj)


@pytest.mark.unit
def test_document_versions_cover_three_docs():
    assert set(DOCUMENT_VERSIONS) == {"terms", "privacy", "student_data"}
    assert STUDENT_DATA_ATTESTATION and "under 13" in STUDENT_DATA_ATTESTATION.lower()


@pytest.mark.unit
def test_has_current_acceptance_true_false():
    assert asyncio.run(has_current_acceptance(_DB(1), "o1", "student_data")) is True
    assert asyncio.run(has_current_acceptance(_DB(0), "o1", "student_data")) is False


@pytest.mark.unit
def test_assert_student_consent_blocks_without_passes_with():
    with pytest.raises(HTTPException) as e:
        asyncio.run(assert_student_consent(_DB(0), "o1"))
    assert e.value.status_code == 403
    assert e.value.detail["code"] == "student_consent_required"
    assert e.value.detail["attestation"]
    # With a recorded consent, the gate passes (no raise).
    asyncio.run(assert_student_consent(_DB(1), "o1"))


@pytest.mark.unit
def test_reconsent_documents_are_terms_and_privacy():
    # student_data is per-ORG (gated on actions); terms/privacy are the per-USER
    # agreements that must be re-accepted on a version bump.
    assert set(RECONSENT_DOCUMENTS) == {"terms", "privacy"}


@pytest.mark.unit
def test_has_current_user_acceptance_true_false():
    assert asyncio.run(has_current_user_acceptance(_DB(1), "u1", "terms")) is True
    assert asyncio.run(has_current_user_acceptance(_DB(0), "u1", "privacy")) is False


@pytest.mark.unit
def test_user_reconsent_needed_all_or_none():
    # No current acceptances -> must re-accept both (post version-bump state).
    assert asyncio.run(user_reconsent_needed(_DB(0), "u1")) == ["terms", "privacy"]
    # Current acceptances -> nothing to re-accept.
    assert asyncio.run(user_reconsent_needed(_DB(1), "u1")) == []


@pytest.mark.unit
def test_record_acceptance_adds_row_and_rejects_unknown_doc():
    db = _DB(0)
    asyncio.run(record_acceptance(db, "o1", "u1", "terms", ip="1.2.3.4"))
    assert len(db.added) == 1
    row = db.added[0]
    assert row.document == "terms" and row.version == DOCUMENT_VERSIONS["terms"]
    assert row.ip_address == "1.2.3.4"
    with pytest.raises(ValueError):
        asyncio.run(record_acceptance(db, "o1", "u1", "bogus"))
