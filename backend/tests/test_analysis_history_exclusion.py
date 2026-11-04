"""Delete from history while keeping published report and analysis records."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.analyses import exclude_analysis_from_history, _get_authorized_analysis


class FakeDB:
    def __init__(self, analysis):
        self.analysis = analysis
        self.committed = 0
        self.added = []

    def get(self, model, analysis_id):
        return self.analysis

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed += 1


def make_user(admin=False):
    return SimpleNamespace(
        id=uuid4(),
        roles=[SimpleNamespace(code="ADMINISTRADOR")] if admin else [],
    )


def test_exclusion_hides_record_without_deleting_it():
    user = make_user()
    analysis = SimpleNamespace(
        created_by_user_id=user.id,
        status="COMPLETED",
        subject_json={"holder_name": "Exemplo"},
    )
    db = FakeDB(analysis)
    response = exclude_analysis_from_history(uuid4(), db, user)
    assert response.status_code == 204
    assert db.committed == 1
    assert analysis.subject_json["holder_name"] == "Exemplo"
    assert analysis.subject_json["_history_archived_at"]
    assert analysis.subject_json["_history_archived_by"] == str(user.id)


def test_cannot_exclude_other_users_record():
    user = make_user()
    analysis = SimpleNamespace(
        created_by_user_id=uuid4(), status="COMPLETED", subject_json={},
    )
    db = FakeDB(analysis)
    with pytest.raises(HTTPException) as exc:
        exclude_analysis_from_history(uuid4(), db, user)
    assert exc.value.status_code == 404
    assert db.committed == 0


def test_cannot_exclude_processing_analysis():
    user = make_user(admin=True)
    analysis = SimpleNamespace(
        created_by_user_id=uuid4(), status="PROCESSING", subject_json={},
    )
    db = FakeDB(analysis)
    with pytest.raises(HTTPException) as exc:
        exclude_analysis_from_history(uuid4(), db, user)
    assert exc.value.status_code == 409
    assert db.committed == 0


def test_exclusion_is_not_repeated_silently():
    user = make_user()
    analysis = SimpleNamespace(
        created_by_user_id=user.id, status="COMPLETED",
        subject_json={"_history_archived_at": "2026-11-04T14:00:00+00:00"},
    )
    with pytest.raises(HTTPException) as exc:
        exclude_analysis_from_history(uuid4(), FakeDB(analysis), user)
    assert exc.value.status_code == 404
