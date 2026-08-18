#!/usr/bin/env python3
"""
diag_segment_alignment.py  —  READ-ONLY.

Why this exists
---------------
The deal-create form reads its segment PICK-LIST from `customer_segments`
(admin "Customer segment options"). The Analytics by_segment dimension buckets
EXISTING deals by their stored `segment`, then runs them through `segment_labels`
(admin "Segment display names"). Those are two different config keys, so editing
the option list does not change what Analytics shows.

This script proves the gap against the LIVE data, with zero mutation. It mirrors
the harness's stdlib-only urllib approach and the same MD persona, so it sees
exactly what /api/pipeline/analytics returns.

Run:
    python scripts\\diag_segment_alignment.py
    python scripts\\diag_segment_alignment.py --base http://127.0.0.1:8502
"""
import argparse
import json
import urllib.error
import urllib.request

ADMIN = {"username": "william001", "password": "EcoStaff0001"}


def _req(base, method, path, token=None, body=None, timeout=30):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw}


def login(base):
    st, body = _req(base, "POST", "/api/auth/login", body=ADMIN)
    tok = (body or {}).get("access_token") or (body or {}).get("token")
    if not tok:
        raise SystemExit(f"login failed (status {st}): {body}")
    return tok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    args = ap.parse_args()
    base = args.base

    print(f"Segment-alignment diagnostic @ {base}\n")
    tok = login(base)

    # --- config (what the admin panels write) -----------------------------
    st, cfg = _req(base, "GET", "/api/pipeline/stages", tok)
    if st != 200:
        raise SystemExit(f"config fetch failed (status {st})")
    cust = cfg.get("customer_segments") or {}
    labels = cfg.get("segment_labels") or {}

    # flatten the per-business-line option list into one set
    configured_options = set()
    for line, opts in cust.items():
        for o in (opts or []):
            configured_options.add(str(o).strip())

    # --- what Analytics actually shows ------------------------------------
    st, an = _req(base, "GET", "/api/pipeline/analytics", tok)
    if st != 200:
        raise SystemExit(f"analytics fetch failed (status {st})")
    by_segment = an.get("by_segment") or []
    analytics_segments = {row.get("segment"): row for row in by_segment}

    # --- report ------------------------------------------------------------
    print("=" * 70)
    print("1) DEAL-FORM OPTIONS  (admin 'Customer segment options' -> customer_segments)")
    print("=" * 70)
    for line, opts in cust.items():
        print(f"   {line:<12} -> {', '.join(opts or []) or '(none)'}")
    print(f"   flattened option set ({len(configured_options)}): "
          f"{', '.join(sorted(configured_options)) or '(none)'}")

    print("\n" + "=" * 70)
    print("2) ANALYTICS DISPLAY MAP  (admin 'Segment display names' -> segment_labels)")
    print("=" * 70)
    if labels:
        for k, v in labels.items():
            print(f"   {k:<16} -> {v}")
    else:
        print("   (empty — Analytics falls back to the built-in Ecobank labels)")

    print("\n" + "=" * 70)
    print("3) WHAT ANALYTICS by_segment ACTUALLY SHOWS  (buckets over live deals)")
    print("=" * 70)
    total = sum(r.get("count", 0) for r in by_segment) or 1
    for r in sorted(by_segment, key=lambda x: x.get("count", 0), reverse=True):
        seg = r.get("segment")
        cnt = r.get("count", 0)
        val = r.get("value", 0.0)
        in_opts = "in option list" if seg in configured_options else "NOT in option list"
        print(f"   {str(seg):<24} {cnt:>5} deals  ({100*cnt/total:4.1f}%)   [{in_opts}]")

    # --- the two gaps ------------------------------------------------------
    shown = set(analytics_segments.keys())
    gap_shown_not_configured = sorted(shown - configured_options)
    gap_configured_no_pipeline = sorted(configured_options - shown)

    print("\n" + "=" * 70)
    print("4) GAP ANALYSIS")
    print("=" * 70)
    print(f"   Segments Analytics shows that are NOT in your option list ({len(gap_shown_not_configured)}):")
    for s in gap_shown_not_configured:
        print(f"       - {s}  ({analytics_segments[s].get('count',0)} deals)")
    if not gap_shown_not_configured:
        print("       (none — every shown segment is a configured option)")

    print(f"\n   Configured options with ZERO pipeline (won't appear in Analytics) ({len(gap_configured_no_pipeline)}):")
    for s in gap_configured_no_pipeline:
        print(f"       - {s}")
    if not gap_configured_no_pipeline:
        print("       (none — every configured option has at least one deal)")

    print("\n" + "=" * 70)
    print("VERDICT")
    print("=" * 70)
    print("   Analytics buckets EXISTING deals by their stored segment, mapped via")
    print("   `segment_labels` — it never reads `customer_segments` (the form options).")
    print("   Editing the option list only changes what NEW deals can store; it does")
    print("   not retag the deals already in the pipeline, nor the display-name map.")
    if gap_shown_not_configured:
        print(f"\n   {len(gap_shown_not_configured)} segment value(s) above are historical/derived and")
        print("   will keep showing until the deals are re-tagged onto your vocabulary.")


if __name__ == "__main__":
    main()
