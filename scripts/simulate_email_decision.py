# -*- coding: utf-8 -*-
"""Round trip a decision by email against stand-in managers.

Sends a case, then replies as the wrong person, as the right person with no
verdict, as the right person with APPROVE, and with a used token. Every one
asserted. It runs in a second and touches no real data - the config and token
files it writes are temporary and removed.

    python scripts/simulate_email_decision.py
"""
import sys, types, json, os, tempfile
sys.path.insert(0, '.')
os.makedirs('data', exist_ok=True)

APP = {"id":"LMS00035","status":"committee_recommended","client_name":"Edward Owiti Okonjo",
       "product":"Personal Loan","amount":4300000,"pipeline_deal_id":"D0868",
       "committee_recommended_by":"B1","history":[]}
USERS = {"jkkorir":{"staff_code":"KE1219","full_name":"KORIR Justus","email":"jkkorir@ecobank.com","role":"Credit Risk Manager"}}
SENT = []; DECIDED = []; JOURNEY = []

class Lam:
    def get(self, i): return APP if i == APP["id"] else None
    def update(self, i, f): APP.update(f)
lms = types.ModuleType("utils.api_lms_routes"); lms._lam = lambda: Lam()
def _decide(app_id, payload, user):
    DECIDED.append((app_id, payload.verdict, payload.reason, user["staff_code"]))
    APP["status"] = "credit_admin" if payload.verdict == "approved" else payload.verdict
    return {"status": APP["status"]}
lms.lms_application_decision = _decide
sys.modules["utils.api_lms_routes"] = lms
models = types.ModuleType("utils.api_lms_models")
class RDR:
    def __init__(self, verdict, authority, reason): self.verdict, self.authority, self.reason = verdict, authority, reason
models.RecordDecisionRequest = RDR; sys.modules["utils.api_lms_models"] = models
core = types.ModuleType("utils.core")
class UM: users = USERS
core.UserManager = UM; sys.modules["utils.core"] = core
notif = types.ModuleType("utils.notifications")
def _send(to, subject, body, attachments=None, **kw): SENT.append((to, subject, kw.get("reply_to"))); return True
notif.send_email = _send; sys.modules["utils.notifications"] = notif
hv = types.ModuleType("utils.handover")
hv.journey = lambda app_id, ev, user, note="", **x: JOURNEY.append((ev, note[:50]))
sys.modules["utils.handover"] = hv
ca = types.ModuleType("utils.core_audit"); ca.audit_log = lambda *a, **k: None
sys.modules["utils.core_audit"] = ca
jn = types.ModuleType("utils.api_lms_journey"); jn.build_case_journey = lambda a: a.get("history", [])
sys.modules["utils.api_lms_journey"] = jn

json.dump({"smtp_host":"x","sender_email":"noreply@ecobank.com","reply_to":"a2z-credit@ecobank.com",
           "decision_secret":"test"}, open("data/email_config.json","w"))
if os.path.exists("data/email_decision_tokens.json"): os.remove("data/email_decision_tokens.json")

import importlib.util
sp = importlib.util.spec_from_file_location("ed", "utils/email_decisions.py")
ed = importlib.util.module_from_spec(sp); sp.loader.exec_module(ed)

print("=" * 80); print("ROUND TRIP: LMS00035 to Korir by email"); print("=" * 80)

r = ed.send_for_decision("LMS00035", "KE1219", {"full_name":"The system","staff_code":""})
tok = r["token"]
print("\n1. SENT")
print("   to       ", r["to"]); print("   reply-to ", SENT[0][2]); print("   subject  ", r["subject"][:60])
print("   journey  ", JOURNEY[-1])
assert SENT[0][2] == "a2z-credit@ecobank.com"

subj = "RE: " + r["subject"]
print("\n2. WRONG SENDER replies APPROVE")
a,t,v,rs = ed.parse_reply(subj, "APPROVE\nfine")
res = ed.record_from_reply(a, t, "somebody.else@gmail.com", v, rs)
print("   refused:", res["why"]); assert not res["ok"] and not DECIDED

print("\n3. KORIR replies with no verdict")
a,t,v,rs = ed.parse_reply(subj, "Will look tomorrow")
res = ed.record_from_reply(a, t, "jkkorir@ecobank.com", v, rs)
print("   ", res["why"]); print("   journey ", JOURNEY[-1]); assert not DECIDED

print("\n4. KORIR replies APPROVE")
a,t,v,rs = ed.parse_reply(subj, "APPROVE\nDSR acceptable, domiciliation confirmed.\n\nOn Wed wrote:\n> quoted")
res = ed.record_from_reply(a, t, "jkkorir@ecobank.com", v, rs)
print("   recorded:", res["ok"]); print("   decision:", DECIDED[-1])
print("   status  :", APP["status"]); print("   journey :", JOURNEY[-1])
assert res["ok"] and APP["status"] == "credit_admin"

print("\n5. THE SAME TOKEN again")
res = ed.record_from_reply(a, t, "jkkorir@ecobank.com", "approved", "again")
print("   refused:", res["why"]); assert not res["ok"] and len(DECIDED) == 1

print("\n" + "=" * 80); print("Every assertion passed.")
os.remove("data/email_config.json"); os.remove("data/email_decision_tokens.json")
