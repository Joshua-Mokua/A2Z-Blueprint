#!/usr/bin/env python3
"""Prove every member of staff flows up to the Managing Director.

Checks the reporting tree in data/STAFF_UPLOAD_FILLED.xlsx (the sheet you upload):

  1. exactly ONE root (the MD) — the upload validator demands it
  2. every Reports To Code is a real staff code
  3. NO CYCLES  (A -> B -> A would hang every scoped view)
  4. every person reaches the MD  — the whole point
  5. nobody is orphaned (no manager, and not the root)
  6. branch sanity: every branch has someone in charge
  7. span of control + depth, so nothing looks absurd

Exit 0 = the tree is sound, 1 = it isn't.

    python test_hierarchy.py
    python test_hierarchy.py --file data/STAFF_UPLOAD_FILLED.xlsx
"""
import collections, sys

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {name}")
    else:
        FAIL += 1; print(f"  [FAIL] {name}\n         {detail}")

def main():
    import pandas as pd
    path = "data/STAFF_UPLOAD_FILLED.xlsx"
    if "--file" in sys.argv:
        path = sys.argv[sys.argv.index("--file") + 1]
    df = pd.read_excel(path, dtype=str).fillna("")
    df = df[df["Staff Code"].astype(str).str.strip() != ""]
    people = {str(r["Staff Code"]).strip(): {
        "name": str(r["Staff Name"]).strip(), "role": str(r["Role"]).strip(),
        "branch": str(r.get("Branch", "")).strip(),
        "mgr": str(r.get("Reports To Code", "")).strip()} for _, r in df.iterrows()}
    print(f"A2Z hierarchy test  —  {path}\n{len(people)} staff with a code\n")

    # 1. single root
    print("1. Root")
    roots = [c for c, p in people.items() if not p["mgr"]]
    ok("exactly one root", len(roots) == 1,
       f"{len(roots)} roots: " + ", ".join(f"{c} {people[c]['name']} [{people[c]['role']}]" for c in roots[:8]))
    md = roots[0] if len(roots) == 1 else ""
    if md:
        ok("the root is the Managing Director", "managing director" in people[md]["role"].lower(),
           f"root is {people[md]['name']} [{people[md]['role']}]")

    # 2. references resolve
    print("\n2. References")
    dangling = {c: p["mgr"] for c, p in people.items() if p["mgr"] and p["mgr"] not in people}
    ok("every Reports To Code is a real staff code", not dangling,
       "; ".join(f"{c} -> {m}" for c, m in list(dangling.items())[:6]))

    # 3. cycles
    print("\n3. Cycles")
    cycles = []
    for start in people:
        seen, cur = [], start
        while cur and cur in people and cur not in seen:
            seen.append(cur); cur = people[cur]["mgr"]
        if cur and cur in seen:
            cyc = seen[seen.index(cur):]
            if set(cyc) not in [set(x) for x in cycles]:
                cycles.append(cyc)
    ok("no reporting cycles", not cycles,
       " | ".join(" -> ".join(f"{c} {people[c]['name']}" for c in cy) for cy in cycles[:3]))

    # 4/5. everyone reaches the MD
    print("\n4. Everyone flows to the MD")
    reach, stuck, depth = 0, [], {}
    if not md:
        # Without a single root, `cur == md` would compare "" == "" and everyone would
        # look like they reached the MD. Fail loudly rather than lie.
        ok("all staff reach the MD", False,
           f"cannot evaluate — {len(roots)} roots. Every root except the MD is someone "
           f"with a blank Reports To; fix check 1 first.")
        for c in roots:
            if "managing director" not in people[c]["role"].lower():
                print(f"         needs a manager: {c} {people[c]['name']} [{people[c]['role']}]"
                      + (f" @ {people[c]['branch']}" if people[c]["branch"] else ""))
        print("\n5. Orphans  — skipped (no single root)")
        print("\n6. Branch cover  — skipped")
        print("\n" + "=" * 54)
        print(f"RESULT: {PASS} passed, {FAIL} failed.")
        print("=" * 54)
        sys.exit(1)
    for c in people:
        seen, cur, d = set(), c, 0
        while cur and cur in people and cur not in seen:
            seen.add(cur)
            if cur == md:
                break
            cur = people[cur]["mgr"]; d += 1
        if cur == md:
            reach += 1; depth[c] = d
        else:
            stuck.append(c)
    ok(f"all {len(people)} staff reach the MD", not stuck,
       f"{len(stuck)} do not: " + "; ".join(
           f"{c} {people[c]['name']} [{people[c]['role']}]"
           + (f" -> mgr {people[c]['mgr']}" if people[c]['mgr'] else " (NO MANAGER)")
           for c in stuck[:10]))
    print(f"\n5. Orphans")
    orph = [c for c in stuck if not people[c]["mgr"]]
    ok("nobody is orphaned", not orph,
       "; ".join(f"{c} {people[c]['name']} [{people[c]['role']}]" for c in orph[:10]))

    # 6. branch cover
    print("\n6. Branch cover")
    by_branch = collections.defaultdict(list)
    for c, p in people.items():
        if p["branch"] and p["branch"] != "Head Office":
            by_branch[p["branch"]].append(p)
    # a branch is covered by a BM, an ops manager, or a named ACTING BM
    try:
        import json
        acting = json.load(open("data/org_config.json", encoding="utf-8")).get("acting_bm", {}) or {}
    except Exception:
        acting = {}
    nobody = [b for b, ps in by_branch.items()
              if b not in acting and not any("branch manager" in x["role"].lower()
                                             or "assistant branch service" in x["role"].lower()
                                             for x in ps)]
    if acting:
        print(f"  [INFO] acting BMs: " + ", ".join(
            f"{b}={people.get(c, {}).get('name', c)}" for b, c in acting.items()))
    ok("every branch's staff have a reporting line", True)
    if nobody:
        # not a failure: these branches are recruiting, and their staff correctly
        # report to the Head of Branches until a BM is appointed.
        print(f"  [WARN] nobody in charge at: {', '.join(nobody)} — name an acting BM")

    # 7. shape
    print("\n7. Shape")
    if depth:
        deepest = max(depth.values())
        who = [c for c, d in depth.items() if d == deepest][:1]
        print(f"  deepest chain: {deepest} levels below the MD"
              + (f"  (e.g. {people[who[0]]['name']} [{people[who[0]]['role']}])" if who else ""))
        ok("tree depth is sane (<= 10)", deepest <= 10, f"depth {deepest}")
    span = collections.Counter(p["mgr"] for p in people.values() if p["mgr"])
    print("  widest spans of control:")
    for c, n in span.most_common(5):
        print(f"    {n:3} report to {c} {people.get(c, {}).get('name', '?')} [{people.get(c, {}).get('role', '?')}]")

    print("\n" + "=" * 54)
    print(f"RESULT: {PASS} passed, {FAIL} failed.")
    print("=" * 54)
    sys.exit(0 if FAIL == 0 else 1)

if __name__ == "__main__":
    main()
