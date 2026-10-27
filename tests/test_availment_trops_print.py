import copy
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from utils import api_credit_admin_routes as routes
from utils.db import db

CASE = 'CASE-PRINT-01'
DATA = {'facility_reference': 'FAC-01'}
ROW = dict(id='MEMO-01', current_version=1, sent_to_trops_by='TROPS-01', sent_to_trops_at='2026-10-27T08:00:00', data=DATA, application_id='APP-01')
SNAPSHOT = dict(version=1, memo=dict(id='MEMO-01', credit_admin_case_id=CASE, application_id='APP-01', data=DATA))

@pytest.fixture
def environment():
    with patch.object(routes, '_authoritative_availment_user', return_value={'role':'TROPS'}), patch.object(routes, '_is_troops', return_value=True) as auth, patch.object(routes, 'require_availment_validation_for_release') as gate, patch.object(db, 'fetch_one') as fetch:
        fetch.side_effect = [copy.deepcopy(ROW), {'snapshot':copy.deepcopy(SNAPSHOT)}]
        yield auth, gate, fetch

def test_released_snapshot(environment):
    auth, gate, fetch = environment
    result = routes.troops_released_availment_memo(CASE, {'username':'operator'})
    assert result['version'] == 1
    assert result['snapshot'] == SNAPSHOT
    gate.assert_called_once_with(CASE, require_released=True)

def test_unreleased_memo_rejected(environment):
    _, _, fetch = environment
    row = dict(ROW, sent_to_trops_at=None)
    fetch.side_effect = [row]
    with pytest.raises(HTTPException) as err:
        routes.troops_released_availment_memo(CASE, {'username':'operator'})
    assert err.value.status_code == 409

def test_missing_snapshot_rejected(environment):
    _, _, fetch = environment
    fetch.side_effect = [ROW, None]
    with pytest.raises(HTTPException) as err:
        routes.troops_released_availment_memo(CASE, {'username':'operator'})
    assert err.value.status_code == 409

def test_content_mismatch_rejected(environment):
    _, _, fetch = environment
    wrong = copy.deepcopy(SNAPSHOT)
    wrong['memo']['data'] = {'facility_reference':'TAMPERED'}
    fetch.side_effect = [ROW, {'snapshot':wrong}]
    with pytest.raises(HTTPException) as err:
        routes.troops_released_availment_memo(CASE, {'username':'operator'})
    assert err.value.status_code == 409

def test_unauthorized_user_rejected(environment):
    auth, gate, fetch = environment
    auth.return_value = {'role':'Branch Manager'}
    with patch.object(routes, '_is_troops', return_value=False):
        with pytest.raises(HTTPException) as err:
            routes.troops_released_availment_memo(CASE, {'username':'operator'})
    assert err.value.status_code == 403
    gate.assert_not_called()
    fetch.assert_not_called()
