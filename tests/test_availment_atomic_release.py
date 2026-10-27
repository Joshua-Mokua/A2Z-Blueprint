import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from utils.credit_admin_db_sync import _wrap_mutation
from utils.db import db

CASE = 'CASE-ATOMIC-01'

def test_missing_postgres_case_fails_closed():
    manager = MagicMock()
    manager.cases = [dict(id=CASE, ready_for_disbursement=True)]
    manager._ca_snapshot = {}
    original = lambda self, case_id, **kwargs: True
    wrapped = _wrap_mutation(original)
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = None
    txn = MagicMock()
    txn.__enter__.return_value = conn
    with patch.dict(os.environ, dict(A2Z_AVAILMENT_TROPS_GATE='enabled')), patch.object(db, 'table_uses_db', return_value=True), patch.object(db, 'transaction', return_value=txn):
        with pytest.raises(HTTPException) as err:
            wrapped(manager, CASE)
    assert err.value.status_code == 409
    assert manager.cases == [dict(id=CASE, ready_for_disbursement=True)]

def test_transaction_failure_restores_in_memory_state():
    manager = MagicMock()
    manager.cases = [dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)]
    manager._ca_snapshot = {}
    original = lambda self, case_id, **kwargs: self.cases[0].update(cleared_for_disbursement=True) or True
    wrapped = _wrap_mutation(original)
    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchone.return_value = ({'id': CASE, 'ready_for_disbursement': True, 'cleared_for_disbursement': False},)
    txn = MagicMock()
    txn.__enter__.return_value = conn
    txn.__exit__.side_effect = RuntimeError('simulated commit failure')
    with patch.dict(os.environ, dict(A2Z_AVAILMENT_TROPS_GATE='disabled')), patch.object(db, 'table_uses_db', return_value=True), patch.object(db, 'transaction', return_value=txn):
        with pytest.raises(RuntimeError, match='simulated commit failure'):
            wrapped(manager, CASE)
    assert manager.cases[0]['cleared_for_disbursement'] is False
    assert manager._ca_snapshot == {}

def test_release_case_write_failure_rolls_back():
    from utils import credit_admin_db_sync as sync
    manager = MagicMock()
    manager.cases = [dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)]
    manager.get.side_effect = lambda cid: next((c for c in manager.cases if c.get("id") == cid), None)
    manager._ca_snapshot = {}
    def clear_for_disbursement(self, case_id, release_actor=None):
        self.get(case_id)["cleared_for_disbursement"] = True
        return True
    wrapped = _wrap_mutation(clear_for_disbursement)
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    data = dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)
    memo = ("MEMO-01", "approved", 1, "CHECKER", "MAKER", "REQUESTER", None, {"facility_reference": "FAC-01"}, "APP-01")
    snapshot = dict(version=1, memo=dict(id="MEMO-01", credit_admin_case_id=CASE, application_id="APP-01", data=memo[7]), approval=dict(approved_by_code="APPROVER", requested_by_code="REQUESTER"))
    cursor.fetchone.side_effect = [(data,), memo, (snapshot,)]
    txn = MagicMock()
    txn.__enter__.return_value = conn
    with patch.dict(os.environ, dict(A2Z_AVAILMENT_TROPS_GATE="enabled")), patch.object(db, "table_uses_db", return_value=True), patch.object(db, "transaction", return_value=txn), patch.object(db, "execute") as execute, patch.object(sync, "_db_sync_credit_admin_case", side_effect=RuntimeError("simulated case write failure")):
        with pytest.raises(RuntimeError, match="simulated case write failure"):
            wrapped(manager, CASE, release_actor=dict(staff_code="RELEASER", name="Officer", role="Credit Admin"))
    execute.assert_called_once()
    assert "sent_to_trops_by" in execute.call_args.args[0]
    assert execute.call_args.kwargs["conn"] is conn
    assert manager.cases[0]["cleared_for_disbursement"] is False
    assert "availment_released_version" not in manager.cases[0]
    assert manager._ca_snapshot == {}
    assert txn.__exit__.call_args.args[0] is RuntimeError

@pytest.mark.parametrize("officer", ["MAKER", "REQUESTER", "CHECKER", "APPROVER"])
def test_release_officer_separation_of_duties(officer):
    manager = MagicMock()
    manager.cases = [dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)]
    manager.get.side_effect = lambda cid: next((c for c in manager.cases if c.get("id") == cid), None)
    manager._ca_snapshot = {}
    def clear_for_disbursement(self, case_id, release_actor=None):
        self.get(case_id)["cleared_for_disbursement"] = True
        return True
    wrapped = _wrap_mutation(clear_for_disbursement)
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    data = dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)
    memo = ("MEMO-01", "approved", 1, "CHECKER", "MAKER", "REQUESTER", None, {"facility_reference": "FAC-01"}, "APP-01")
    snapshot = dict(version=1, memo=dict(id="MEMO-01", credit_admin_case_id=CASE, application_id="APP-01", data=memo[7]), approval=dict(approved_by_code="APPROVER", requested_by_code="REQUESTER"))
    cursor.fetchone.side_effect = [(data,), memo, (snapshot,)]
    txn = MagicMock()
    txn.__enter__.return_value = conn
    with patch.dict(os.environ, dict(A2Z_AVAILMENT_TROPS_GATE="enabled")), patch.object(db, "table_uses_db", return_value=True), patch.object(db, "transaction", return_value=txn), patch.object(db, "execute") as execute:
        with pytest.raises(HTTPException) as err:
            wrapped(manager, CASE, release_actor=dict(staff_code=officer, name="Officer", role="Credit Admin"))
    assert err.value.status_code == 403
    execute.assert_not_called()
    assert manager.cases[0]["cleared_for_disbursement"] is False
    assert "availment_released_version" not in manager.cases[0]
    assert txn.__exit__.call_args.args[0] is HTTPException

def test_independent_officer_successful_atomic_release():
    from utils import credit_admin_db_sync as sync
    manager = MagicMock()
    manager.cases = [dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)]
    manager.get.side_effect = lambda cid: next((c for c in manager.cases if c.get("id") == cid), None)
    manager._ca_snapshot = {}
    def clear_for_disbursement(self, case_id, release_actor=None):
        self.get(case_id)["cleared_for_disbursement"] = True
        return True
    wrapped = _wrap_mutation(clear_for_disbursement)
    conn = MagicMock()
    cursor = conn.cursor.return_value.__enter__.return_value
    data = dict(id=CASE, ready_for_disbursement=True, cleared_for_disbursement=False)
    memo = ("MEMO-01", "approved", 2, "CHECKER", "MAKER", "REQUESTER", None, {"facility_reference": "FAC-01"}, "APP-01")
    snapshot = dict(version=2, memo=dict(id="MEMO-01", credit_admin_case_id=CASE, application_id="APP-01", data=memo[7]), approval=dict(approved_by_code="APPROVER", requested_by_code="REQUESTER"))
    cursor.fetchone.side_effect = [(data,), memo, (snapshot,)]
    txn = MagicMock()
    txn.__enter__.return_value = conn
    with patch.dict(os.environ, dict(A2Z_AVAILMENT_TROPS_GATE="enabled")), patch.object(db, "table_uses_db", return_value=True), patch.object(db, "transaction", return_value=txn), patch.object(db, "execute") as execute, patch.object(sync, "_db_sync_credit_admin_case") as save_case:
        result = wrapped(manager, CASE, release_actor=dict(staff_code="INDEPENDENT", name="Independent Officer", role="Credit Admin"))
    assert result is True
    assert manager.cases[0]["cleared_for_disbursement"] is True
    assert manager.cases[0]["availment_released_version"] == 2
    assert manager.cases[0]["availment_released_by"] == "INDEPENDENT"
    execute.assert_called_once()
    assert execute.call_args.args[1] == ("INDEPENDENT", "MEMO-01")
    assert execute.call_args.kwargs["conn"] is conn
    save_case.assert_called_once()
    assert save_case.call_args.kwargs["conn"] is conn
    assert save_case.call_args.args[0]["availment_released_version"] == 2
    assert txn.__exit__.call_args.args == (None, None, None)
