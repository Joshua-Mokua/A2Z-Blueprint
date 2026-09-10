# -*- coding: utf-8 -*-
"""Exercise utils/handover.py against stand-in managers.

Six cases, every one asserted. Run it after any change to the return path -
it takes a second and it found a real fault the compile check could not:
credit admin asking for a document was moving the deal while leaving the case,
which is the stage-versus-status divergence the module exists to end.

    python scripts/simulate_handover.py

Touches no data. It stubs the managers, so it can run anywhere.
"""
import sys, types, datetime
sys.path.insert(0, '.')

APP = {}
DEAL = {}
SENT = []
AUDIT = []

class FakeLam:
    def get(self, app_id): return APP if APP.get("id") == app_id else None
    def update(self, app_id, fields):
        APP.update(fields); APP["last_updated"] = "now"; return True

class FakePM:
    def get_deal(self, did): return DEAL if DEAL.get("id") == did else None
    def update_stage(self, did, stage, note, by):
        DEAL["_history"] = DEAL.get("_history", []) + [(DEAL["stage"], stage, note[:40])]
        DEAL["stage"] = stage

FLOW = ["Initiation","Documentation","Rework","Branch Credit Committee Review",
        "Department Credit Analysis","Department Credit Committee Review",
        "Credit Analysis","Offer Letter","Credit Administration","Trops",
        "Closed Won","Closed Lost"]

# Stub the modules handover imports lazily.
lms = types.ModuleType("utils.api_lms_routes"); lms._lam = lambda: FakeLam()
sys.modules["utils.api_lms_routes"] = lms
core = types.ModuleType("utils.core"); core.PipelineManager = FakePM
sys.modules["utils.core"] = core
api = types.ModuleType("utils.api")
api._stage_flow_for = lambda p: FLOW
api._product_document_config = lambda d: ([], "Documentation")
sys.modules["utils.api"] = api
notif = types.ModuleType("utils.notifications")
def _ns(code, subj, body): SENT.append((code, subj)); return True
notif.notify_staff = _ns
sys.modules["utils.notifications"] = notif
ca = types.ModuleType("utils.core_audit")
ca.audit_log = lambda a,u,d="": AUDIT.append((a,d[:40]))
sys.modules["utils.core_audit"] = ca

import importlib.util
spec = importlib.util.spec_from_file_location("hv", "utils/handover.py")
hv = importlib.util.module_from_spec(spec); spec.loader.exec_module(hv)

USER = {"staff_code":"KE1219","full_name":"KORIR Justus","username":"jkkorir"}

def reset(stage):
    APP.clear(); DEAL.clear(); SENT.clear(); AUDIT.clear()
    APP.update({"id":"LMS00099","status":"referred_to_committee",
                "pipeline_deal_id":"D0999","rm_code":"KE1262","rm_name":"KENDI Glory"})
    DEAL.update({"id":"D0999","stage":stage,"product_type":"Personal Loan"})

print("=" * 84)
print("SIMULATION: send_back and bring_back")
print("=" * 84)

# 1. Credit risk sends back to the owner, nobody named.
reset("Credit Analysis")
r = hv.send_back("LMS00099", to=None, reason="Signed offer letter is missing",
                 user=USER, asked_from="credit risk")
print("\n1. credit risk -> nobody named (falls back to the owner)")
print("   returned to      ", r["returned_to"])
print("   froze at         ", r["froze_at_stage"])
print("   deal is now at   ", DEAL["stage"])
print("   case status      ", APP["status"])
print("   assigned to      ", APP["analyst"]["code"])
print("   emails sent      ", SENT)
assert r["returned_to"] == ["KE1262"], "should fall back to the owner"
assert r["froze_at_stage"] == "Credit Analysis"
assert DEAL["stage"] == "Rework"
assert APP["status"] == "returned"
assert SENT and SENT[0][0] == "KE1262"

# 2. Bring it back.
r2 = hv.bring_back("LMS00099", {"staff_code":"KE1262","full_name":"KENDI Glory","username":"g"})
print("\n2. the owner finishes and it comes back")
print("   deal restored to ", DEAL["stage"])
print("   back to          ", r2["back_to"])
print("   status           ", APP["status"])
print("   emails sent      ", SENT[-1:])
assert DEAL["stage"] == "Credit Analysis", "must return where it froze"
assert r2["back_to"] == "KE1219"
assert APP["status"] == "assigned"

# 3. Several people at once, from the analyst's desk.
reset("Department Credit Analysis")
r = hv.send_back("LMS00099", to=["KE1262", {"code":"KE1300","name":"MUTISYA Catherine"}],
                 reason="Redo the DSR and attach the payslip", user=USER,
                 asked_from="analyst", reasons=["DSR outside policy"])
print("\n3. two people at once")
print("   returned to      ", r["returned_to"])
print("   assigned to      ", APP["analyst"]["code"], "(the first named)")
print("   emails sent      ", [c for c,_ in SENT])
print("   rework reasons   ", APP.get("rework_reasons"))
assert r["returned_to"] == ["KE1262","KE1300"]
assert len(SENT) == 2

# 4. Credit admin keeps the case - status untouched.
reset("Credit Administration")
r = hv.send_back("LMS00099", to="KE1262", reason="Open the loan account please",
                 user={"staff_code":"KE956","full_name":"Sera","username":"s"},
                 asked_from="credit admin", set_status=False)
print("\n4. credit admin asks but keeps the case")
print("   case status      ", APP["status"], "(unchanged)")
print("   deal is at       ", DEAL["stage"])
print("   emails sent      ", [c for c,_ in SENT])
assert APP["status"] == "referred_to_committee", "status must not change"

# 5. Refusals.
reset("Credit Analysis")
print("\n5. what it refuses")
for reason, label in (("", "no reason"), ("fix", "too short")):
    try:
        hv.send_back("LMS00099", to="KE1262", reason=reason, user=USER,
                     asked_from="credit risk")
        print("   %-12s ACCEPTED - wrong" % label); raise SystemExit(1)
    except ValueError as e:
        print("   %-12s refused: %s" % (label, str(e)[:44]))

# 6. A closed deal is never reopened.
reset("Closed Won")
r = hv.send_back("LMS00099", to="KE1262", reason="Something is missing",
                 user=USER, asked_from="credit risk")
print("\n6. a closed deal")
print("   deal stayed at   ", DEAL["stage"])
assert DEAL["stage"] == "Closed Won", "a closed deal must not move"

print("\n" + "=" * 84)
print("Every assertion passed.")
