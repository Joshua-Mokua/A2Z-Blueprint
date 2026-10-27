"""Stage 11: opt-in CAD memo validation inbox and electronic attestation.

No disbursement authorization is provided. Role assignments are explicit staff codes,
not inferred from JWT role strings. Physical signatures require a separate evidence
verification workflow and are deliberately not accepted here.
"""
from __future__ import annotations
import json
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from utils.auth_jwt import get_current_user
from utils.core import UserManager
from utils.db import db
from utils.availment_dual_validation import configure, attest, readiness, ValidationConflict, _identity

router = APIRouter(prefix="/api/credit-admin")

def _enabled():
    if os.getenv('A2Z_AVAILMENT_VALIDATION_API', '').strip() != 'enabled':
        raise HTTPException(404, 'Validation workflow is not enabled')

def _staff(claims):
    key = str((claims or {}).get('username') or '').strip()
    users = UserManager().users
    record = users.get(key)
    if not isinstance(record, dict) or record.get('active') is not True:
        raise HTTPException(403, 'Active staff account required')
    return {**record, 'username': key}

def _policy():
    # Administrator must supply approved mappings, never trust role names in tokens.
    raw = os.getenv('A2Z_AVAILMENT_VALIDATOR_POLICY', '')
    try:
        policy = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(503, 'Approved validator policy is not configured')
    if not isinstance(policy, dict) or not policy:
        raise HTTPException(503, 'Approved validator policy is not configured')
    normalized = {}
    for role, code in policy.items():
        if not isinstance(role, str) or not role.strip() or not isinstance(code, str) or not code.strip():
            raise HTTPException(503, 'Invalid validator policy')
        normalized[role.strip()] = code.strip().casefold()
    if len(set(normalized.values())) != len(normalized):
        raise HTTPException(503, 'Separation-of-duties violation in validator policy')
    return normalized

def _case_grants(case_id):
    """Explicit, case-scoped assignments. Never infer access from global role labels.

    Fail closed unless a case-specific grant is configured by an administrator.
    """
    raw = os.getenv('A2Z_AVAILMENT_CASE_GRANTS', '')
    try:
        grants = json.loads(raw)
    except (ValueError, TypeError):
        raise HTTPException(503, 'Case validator assignments are not configured')
    if not isinstance(grants, dict) or not isinstance(grants.get(case_id), dict):
        raise HTTPException(403, 'No authorization for this case')
    mapping = grants[case_id]
    if not mapping or any(not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip() for k,v in mapping.items()):
        raise HTTPException(503, 'Invalid case validator assignments')
    result = {k.strip(): v.strip().casefold() for k,v in mapping.items()}
    if len(set(result.values())) != len(result):
        raise HTTPException(503, 'Case assignment violates separation of duties')
    return result

def _authorize_case(case_id, staff, role):
    grants = _case_grants(case_id)
    if grants.get(role) != _identity(staff):
        raise HTTPException(403, 'Not assigned to this role on this case')
    return grants

def _memo(case_id):
    row = db.fetch_one('SELECT data, status FROM credit.availment_memos WHERE credit_admin_case_id=%s', (case_id,))
    if not row:
        raise HTTPException(404, 'Memo not found')
    data = row['data']
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        raise HTTPException(409, 'Invalid memo data')
    return data, row['status']

class ConfigureRequest(BaseModel):
    mode: str
    required_roles: list[str] = Field(min_length=1)

class DecisionRequest(BaseModel):
    role: str
    action: str
    note: str = ''

@router.get('/availment-validation/inbox')
def validation_inbox(claims=Depends(get_current_user)):
    _enabled()
    staff = _staff(claims)
    policy = _policy()
    my_roles = [r for r, code in policy.items() if code == _identity(staff)]
    if not my_roles:
        return {'items': []}
    rows = db.fetch_all("SELECT credit_admin_case_id, status, data FROM credit.availment_memos WHERE status IN ('draft','ready_for_approval')")
    items = []
    for row in rows:
        data = row['data']
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            continue
        case_id = str(row['credit_admin_case_id'])
        try:
            case_roles = _case_grants(case_id)
        except HTTPException:
            continue
        assigned_roles = {r for r, code in case_roles.items() if code == _identity(staff)} & set(my_roles)
        if not assigned_roles:
            continue
        ledger = data.get('dual_validation') or {}
        if ledger.get('mode') != 'electronic':
            continue
        pending = assigned_roles & set(readiness(data)['missing_roles'])
        if pending and not readiness(data)['blocked']:
            items.append({'case_id': row['credit_admin_case_id'], 'roles': sorted(pending), 'status': row['status']})
    return {'items': items}

@router.post('/cases/{case_id}/availment-validation/configure')
def validation_configure(case_id: str, payload: ConfigureRequest, claims=Depends(get_current_user)):
    _enabled()
    staff = _staff(claims)
    policy = _policy()
    # Only configured CAD maker may configure. Not a JWT-supplied role.
    if policy.get('CAD Maker') != _identity(staff):
        raise HTTPException(403, 'Designated CAD maker required')
    _authorize_case(case_id, staff, 'CAD Maker')
    if payload.mode not in {'electronic','physical'}:
        raise HTTPException(422, 'Only physical or electronic mode supported')
    if not set(payload.required_roles) <= set(policy):
        raise HTTPException(422, 'Unmapped validation role')
    case_grants = _case_grants(case_id)
    if not set(payload.required_roles) <= set(case_grants):
        raise HTTPException(422, 'Required role has no case-specific assignee')
    if any(case_grants[r] != policy[r] for r in payload.required_roles):
        raise HTTPException(409, 'Case assignee differs from approved validator policy')
    try:
        return configure(case_id, staff, payload.mode, payload.required_roles)
    except ValidationConflict as exc:
        raise HTTPException(409, str(exc)) from exc

@router.post('/cases/{case_id}/availment-validation/decision')
def validation_decision(case_id: str, payload: DecisionRequest, claims=Depends(get_current_user)):
    _enabled()
    staff = _staff(claims)
    policy = _policy()
    if policy.get(payload.role) != _identity(staff):
        raise HTTPException(403, 'Not assigned to this validation role')
    _authorize_case(case_id, staff, payload.role)
    data, _ = _memo(case_id)
    if (data.get('dual_validation') or {}).get('mode') != 'electronic':
        raise HTTPException(409, 'Physical signatures require independently verified evidence')
    try:
        return attest(case_id, staff, payload.role, payload.action, note=payload.note)
    except ValidationConflict as exc:
        raise HTTPException(409, str(exc)) from exc

@router.get('/cases/{case_id}/availment-validation/readiness')
def validation_readiness(case_id: str, claims=Depends(get_current_user)):
    _enabled()
    staff = _staff(claims)
    policy = _policy()
    if _identity(staff) not in policy.values():
        raise HTTPException(403, 'Not a configured validator')
    grants = _case_grants(case_id)
    if _identity(staff) not in grants.values():
        raise HTTPException(403, 'No case-level access')
    data, _ = _memo(case_id)
    return readiness(data)
