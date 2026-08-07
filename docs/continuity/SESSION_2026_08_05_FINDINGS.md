# Session Findings — 2026-08-05 (Credit Segment Isolation + LMS Dual-Store)

## SHIPPED (committed + pushed, live on Alex's pull)
- View-only document permissions: owner+Admin edit, everyone else view-only (1e6772a, 2179696, 093440d)
- Two-level funnel: Consumer/Commercial/CIB business-unit selector then sub-segments (b5f9826)
- Copy cleanup: loose dev subtitle on Analytics (cda8400)
- LMS pagination (prev/next) + Decided count fix (add disbursed, drop returned) + removed v10.582 stamp (7d3d519)
- **Credit segment isolation** (a319e93): Dept Analysts see ONLY their segment; role+department aware;
  all visibility paths gated (rm_code + pool branches, filter + is_app_in_scope).
  VERIFIED SAFE for unstamped apps (seg='' = not hidden) — cannot break the bank.

## CONFIRMED CORRECT (our side)
- Consumer team ALL see the same Consumer book (110 codes) then filter: Head Premier, Premier RM,
  Head of Consumer, Consumer RM all get identical 110-Consumer scope. Includes all Consumer HO
  leadership (Lunar/Head of Sales, Annette/Consumer Products, Robert Githaiga/Digital, Nyaberi/Head
  of Direct). ZERO Consumer HO staff missing. Design matches Josh's intent.
- Segment gate resolution: Catherine KE1300->consumer, Brian KE1305/Dennis KE1348->commercial,
  Nyamai KE1315/Loise KE1034->cib, Justus KE1219/Thomas KE820->'' (no restriction, see all).

## THE BIG DISCOVERY — LMS DUAL-STORE (root cause, needs Path 1)
- **LoanApplicationManager (core.py:5473) reads loan_applications.JSON, NOT the DB** — no DB path,
  ignores TABLE_USE_DB['loan_applications']=True.
- **DB table (724 apps)**: RICH realistic data (Strathmore, Kenya Airways, varied products, all stages),
  now correctly re-attributed to real analysts by segment + metadata.segment stamped. THE GOOD DATA.
- **JSON file (738 apps)**: SIM junk ("SIM Acme Ltd", 730x "Term Loan", analyst immaculate0716). The
  live app reads THIS. Josh's demo looked wrong because of this.
- The DB re-attribution I did (reattribute_lms.py, step1_segment_backfill.py) is CORRECT but invisible
  (wrote DB, app reads JSON). JSON re-attribution was tried, skewed (classifier didn't fit SIM data),
  and REVERTED to pristine backup.

## PATH 1 — THE PROPER FIX (next focused session)
Make LoanApplicationManager DB-first (mirror PipelineManager's proven pattern):
- _load() -> read DB when table_uses_db('loan_applications'), JSON fallback
- ALL write methods (save, update, submit_to_credit, record_decision, request_info, escalate,
  add_bcc_record, issue_offer, refer_to_committee, resolve_committee, create_from_pipeline_deal, +~15
  more at core.py:5485-5950) -> DB-aware, or reads/writes diverge again.
- Template exists: PipelineManager (core.py:4075+) already does DB-first.
- After switch: the good 724 (re-attributed, segment-stamped) go live; segment isolation activates.
- This ALSO permanently fixes the "works here/off at bank" risk for LMS.

## PENDING (smaller, after Path 1 or independent)
- **Step 4 — incoming visibility**: add 'draft','completeness' to lms_config.json pool_visibility.statuses
  (analysts see pre-validation cases for prep). VIA MERGE SCRIPT (lms_config.json is skip-worktree).
- **Credit Risk pool-roles fix**: pool_visibility.roles has 'credit risk management' but Justus's ROLE
  is 'Credit Risk Manager' — substring mismatch, _role_sees_pool=False. Add 'credit risk manager' +
  'credit risk' to roles. Same merge script.
- **DSA filter** (Josh): DSAs = CN-coded contract staff, visibility mapped to Luna (Head of Sales).
  Want a DSA selection/filter on Consumer & Commercial views; DSA business visible to Luna + segment.
- Analyst-override branch: analyst stored as JSON STRING in a varchar column (not jsonb). The visibility
  filter checks isinstance(analyst,dict) — works IF the loader parses it. Verify post-Path-1.

## BANK ISSUE (Fiona / Consumer) — AWAITING ALEX
- Fiona (KE1269, Head Premier Banking, Consumer) sees nothing on Consumer at the bank.
- OUR SIDE IS CORRECT: scope healthy (110 Consumer), segment gate doesn't restrict her (=''),
  gate safe for unstamped apps, configs skip-worktree (didn't clobber Alex).
- => ENVIRONMENTAL at bank. Likely: (1) API not restarted after pull [try first], (2) bank deals
  lack client_type -> empty Consumer book, (3) bank roster differs, (4) per-clone skip-worktree not set.
- ACTION: Alex restart API + hard-refresh; if not fixed run ALEX_diagnose_consumer.py; confirm if
  only Fiona or all Consumer staff.

## KEY LESSON (reinforced, painful)
Before mutating credit data: INSTRUMENT WHICH STORE THE LIVE ENDPOINT READS. Spent this session
re-attributing the DB when the LMS app reads JSON — the same dual-store lesson from pipeline_deals.
The manager class can silently ignore TABLE_USE_DB. Check the actual read path, don't assume the flag.
