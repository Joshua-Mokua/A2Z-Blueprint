"""Dual-mode availment validation ledger, PostgreSQL-backed, fail-closed.

This module does not grant authority to release funds. Integrators must verify
role and document permissions at the API boundary and use release_ready only
as one input to the TROPS authorization checks.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from utils.db import db

MODES = {'physical', 'electronic'}
ACTIONS = {'validate', 'return', 'reject'}

class ValidationConflict(ValueError):
    pass

def _identity(user: dict) -> str:
    return str(user.get('staff_code') or user.get('username') or '').strip().casefold()

def _decode(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValidationConflict('Invalid memo JSON data')

def _locked(conn, case_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute('SELECT id, status, current_version, data, created_by FROM credit.availment_memos WHERE credit_admin_case_id = %s FOR UPDATE', (case_id,))
        row = cur.fetchone()
    if not row:
        raise ValidationConflict('Availment memo not found')
    return dict(zip(('id','status','current_version','data','created_by'), row))

def _write(conn, case_id: str, data: dict, actor: str) -> None:
    db.execute('UPDATE credit.availment_memos SET data=%s::jsonb, updated_by=%s, updated_at=now() WHERE credit_admin_case_id=%s', (json.dumps(data), actor, case_id), conn=conn)

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _digest(data: dict) -> str:
    # Snapshot includes the exact content being attested, excluding the validation ledger.
    material = {k:v for k,v in data.items() if k != 'dual_validation'}
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()

def configure(case_id: str, user: dict, mode: str, required_roles: list[str]) -> dict:
    """Configure a draft only; caller must authorize CAD maker and role policy."""
    if mode not in MODES:
        raise ValidationConflict('Hybrid mode is not approved or enabled')
    roles = [str(r).strip() for r in required_roles]
    if not roles or any(not r for r in roles) or len(set(roles)) != len(roles):
        raise ValidationConflict('Unique, nonempty required validation roles are mandatory')
    actor = _identity(user)
    if not actor:
        raise ValidationConflict('Authenticated staff code required')
    with db.transaction() as conn:
        memo = _locked(conn, case_id)
        if memo['status'] != 'draft':
            raise ValidationConflict('Only a draft memo can configure validation')
        data = _decode(memo['data'])
        existing = data.get('dual_validation') or {}
        if existing.get('decisions'):
            raise ValidationConflict('Existing attestations cannot be silently discarded')
        data['dual_validation'] = {'mode': mode, 'required_roles': roles, 'snapshot_hash': _digest(data), 'decisions': [], 'configured_by': actor, 'configured_at': _now()}
        _write(conn, case_id, data, actor)
    return data['dual_validation']

def attest(case_id: str, user: dict, role: str, action: str, *, evidence_ref: str = '', note: str = '', verified_evidence: bool = False) -> dict:
    """Record a decision. Caller must independently verify user is authorized for role.

    For physical mode, evidence_ref must point to an already verified signed artifact.
    This module cannot itself verify signatures or document bytes.
    """
    actor = _identity(user)
    if not actor or action not in ACTIONS:
        raise ValidationConflict('Authenticated actor and valid decision required')
    with db.transaction() as conn:
        memo = _locked(conn, case_id)
        if memo['status'] not in {'draft','ready_for_approval'}:
            raise ValidationConflict('Memo is not in a valid validation state')
        data = _decode(memo['data'])
        ledger = data.get('dual_validation')
        if not isinstance(ledger, dict) or role not in ledger.get('required_roles', []):
            raise ValidationConflict('Validation role not configured')
        if _digest(data) != ledger.get('snapshot_hash'):
            raise ValidationConflict('Memo content changed; reconfiguration required')
        if action == 'validate' and ledger['mode'] == 'physical' and (not evidence_ref.strip() or not verified_evidence):
            raise ValidationConflict('Physical validation requires verified signed-document evidence')
        if action in {'return','reject'} and not note.strip():
            raise ValidationConflict('Reason required')
        if any(d['role'] == role and d['action'] == 'validate' for d in ledger.get('decisions', [])):
            raise ValidationConflict('Role already validated this memo version')
        if any(d['actor'] == actor and d['role'] != role for d in ledger.get('decisions', [])):
            raise ValidationConflict('Same staff member cannot attest for multiple roles')
        decision = {'role': role, 'actor': actor, 'action': action, 'mode': ledger['mode'], 'evidence_ref': evidence_ref.strip() if ledger['mode']=='physical' else '', 'note': note.strip(), 'at': _now(), 'snapshot_hash': ledger['snapshot_hash']}
        ledger['decisions'].append(decision)
        _write(conn, case_id, data, actor)
    return decision

def readiness(data: dict) -> dict:
    ledger = data.get('dual_validation') or {}
    required = set(ledger.get('required_roles') or [])
    decisions = ledger.get('decisions') or []
    validated = {d['role'] for d in decisions if d.get('action') == 'validate' and d.get('snapshot_hash') == ledger.get('snapshot_hash')}
    blockers = [d for d in decisions if d.get('action') in {'return','reject'}]
    ready = bool(required) and required <= validated and not blockers and _digest(data) == ledger.get('snapshot_hash')
    return {'validation_complete': ready, 'missing_roles': sorted(required - validated), 'blocked': bool(blockers)}
