# HQ Canonical Extension + hr.json Dedup

**Version anchor:** v10.398 (May 2026)
**Phase:** Phase C2 admin-precursor batch
**Per:** Joshua's directive 2026-05-13 — every HQ role mapped to a chief
**Audit:** G284 added
**Resolves:** TC42 (HQ canonical incompleteness)

## Part 1 — Problem

After v10.397's cascade regeneration, 53 critical rep-sender findings remained — all HQ specialist roles (CFO, CRO, CIO, COO, CHRO, etc.) whose canonical subordinates weren't defined. These chiefs received cascade from MD but couldn't send onward because the canonical didn't say what they manage.

Joshua's directive: map every HQ role to a chief so the cascade reaches every staff member.

Plus: hr.json still had 8 duplicate staff_codes (synthetic test data collisions).

## Part 2 — Solution

### 2a. hr.json dedup (8 collisions fixed)

```
300004 → 901000 (Area Manager vs Senior RM Corporate)
300200 → 901001 (RM SME vs SRM SME)
300238 → 901002 (COO vs SRM SME)
300328 → 901003 (RM Corporate vs Senior Manager Direct Sales Force)
301021 → 901004 (Chief Credit Officer vs Head Of Corporates & TF)
301093 → 901005 (Area Manager vs Area Manager)
301141 → 901006 (Head of MSME vs Area Manager)
301235 → 901007 (SRM SME vs RM Corporate)
```

All three staff lists (users.json + staff_register.xlsx + hr.json) now clean.

### 2b. HQ canonical extension (130 entries, was 27)

**4 new chiefs added to canonical:**
- Chief Commercial Officer (CCO)
- Chief Credit Officer
- Chief Internal Auditor (Chief Audit per Joshua)
- General Manager - Bancassurance

**Chief Compliance Officer → CRO** per Joshua's "compliance reports here" directive (overrides the general "chiefs report to MD" rule).

**Bancassurance Officer dual-reporting**: Branch Manager primary (same-branch via regenerator) + General Manager - Bancassurance fallback (HQ + dotted line for branch-located).

### 2c. Engine detector refinement

Pre-v10.398, the rep-sender detector flagged ANY role with ≥2 staff and 0 senders as critical. This over-flagged leaf roles (Tellers have 244 staff, 0 senders — but Tellers are leaves; they don't send).

v10.398 refinement: only flag roles that appear as managers in canonical `role_manager_whitelist`. Leaf roles are now correctly ignored.

Result: the TRUE signal surfaces. Post-v10.398: 0 critical findings = HQ canonical complete.

## Part 3 — Subtree summary

**MD → all 12 chiefs + GM Bancassurance + Company Secretary and Chief Legal Officer**

| Chief | Subtree |
|---|---|
| **CFO** | Financial Controller, Finance Manager, Tax Manager, Business Analytics; Head of Treasury → Senior Manager Treasury → Forex Trader, Treasury Dealers, Corporate Sales Dealer |
| **CRO** | Risk Manager → Operational Risk Manager; Chief Compliance Officer → Senior Manager Compliance → Regulatory Compliance Officer |
| **CIO** | Head of ICT → Database/Network/Core Banking/Sys Admin Managers + technical officers; Head of DFS → Manager Agency/Mobile/Card Operations → Senior Digital Channels Officer |
| **COO** | Head of Operations → Central Processing + Clearing + Cash Centre + Trade Finance Ops; Head of Marketing → Marketing Officers; Head of Procurement; Head Customer Experience; Facilities |
| **CHRO** | All HRBP roles (Operations, Payroll, Admin, OSH, Performance & HRIS, Training) + HR Officer Admin |
| **CRBO** (extended) | Head of Branches + Head of Women Banking + Senior Manager Diaspora → RM Diaspora + Senior Manager Direct Sales Force (Business Dev = DSR oversight) |
| **CCO** (NEW) | Head of Corporates & Trade Finance + Head of MSME + Head of GIB → all RMs |
| **Chief Credit Officer** (NEW) | Senior Manager Credit Analysis + Credit Admin + Credit Monitoring + Collections & Recoveries |
| **Chief Internal Auditor** | Senior Manager Internal Audit → Internal Auditors |
| **Chief Legal Officer** | Manager Legal → Legal Officers |
| **GM Bancassurance** (NEW) | Manager Underwriting + HQ Bancassurance; branch Bancassurance Officers via dotted line |

## Part 4 — Engine audit before/after

| Metric | v10.397 | v10.398 |
|---|---|---|
| Cycles | 0 | 0 ✓ |
| Cross-branch | 0 | 0 ✓ |
| Multi-sender | 0 | 0 ✓ |
| Rep critical | **53 (TC42)** | **0** ✓ |
| Rep warn | 0 | 2 (acceptable) |
| Cascade entries | 23,069 | 25,488 |

## Part 5 — Hanging roles for Joshua

7 best-effort assignments need confirmation:

1. Synthetic "Managing Director" — keep/delete? (C1)
2. Trade Finance split — CCO-relationship vs COO-operations boundary
3. Head of DFS — CIO vs COO
4. Manager Card Operations — DFS/CIO vs COO
5. Corporate Sales Dealer — Treasury (CFO) vs CCO
6. Trade Finance Back Office Manager — COO vs CFO
7. "Admin" generic role — CHRO vs MD

Production-time admin UI (v10.399) makes these reconfigurable.

## Part 6 — Architectural pattern

v10.395 (dynamic engine) → v10.396 (canonical aligned) → v10.397 (cascade regen) → v10.398 (canonical complete) is the canonical-driven design progressing through 4 stages:

1. **Read** canonical (v10.395)
2. **Align** canonical to truth (v10.396)
3. **Apply** canonical to data (v10.397)
4. **Extend** canonical to full coverage (v10.398)

Next:
5. **Edit** canonical from admin UI (v10.399)

## Part 7 — Honest notes

1. **3 staff lists harmonised** = tests have clean data.
2. **4 new chiefs in canonical** = every HQ role has a chief.
3. **Detector refined** = 0 critical findings reflects TRUE state.
4. **2 warn findings** for RM Corporate / SRM Corporate primary selection — round-robin improvement future.
5. **7 hanging roles** — production admin UI will let Joshua reconfigure.
