#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
WP1 - the warehouse client asks for a PAGE. Targeted, not a whole-file embed.

The shelf holds 12,591 records and is aiming at a million. The endpoint already
returns a window; this is the client half - the one function that asks for it.

WHY THIS IS NOT IN UI2: UI2 carries whole files, and my copy of api.ts is older
than the pilot's - it has no fetchRatePool, no approveRateRequest, none of the
Treasury Rate Desk. Applying it would have DELETED them, silently, and the
first anybody knew would be a blank Treasury page.

That is the whole-file trap, arriving for the third time. An anchored edit can
only do what it says, so this is anchored.

Adds `limit` and `offset` to the request, and `shown`, `limit`, `offset` and
`has_more` to the response type - so the page can say "1-200 of 12,591" and
move through the shelf.

Usage (from project root, .venv active):
    python scripts\patch_wp1_warehouse_paging.py            # dry run
    python scripts\patch_wp1_warehouse_paging.py --apply
"""
import os
import shutil
import sys

API = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_wp1"

OLD = '''export async function fetchWarehouseShelves(
  opts: { town?: string; sector?: string; q?: string } = {},
): Promise<{ shelves: Record<string, WarehouseProspect[]>; total: number }> {
  const qs = new URLSearchParams();
  if (opts.town) qs.set('town', opts.town);
  if (opts.sector) qs.set('sector', opts.sector);
  if (opts.q) qs.set('q', opts.q);
  const s = qs.toString();
  return getJson<{ shelves: Record<string, WarehouseProspect[]>; total: number }>(
    `/warehouse/shelves${s ? `?${s}` : ''}`);
}'''

NEW = '''/** A PAGE of the shelf.
 *
 *  `total` is what the FILTER matches; `shown` is what came back in this page.
 *  At 12,591 records the endpoint can no longer send everything - the page
 *  spun and then showed an empty shelf - so it asks for a window and moves
 *  through it. A page then costs the same whether the shelf holds a thousand
 *  rows or a million.
 */
export async function fetchWarehouseShelves(
  opts: { town?: string; sector?: string; q?: string;
          limit?: number; offset?: number } = {},
): Promise<{
  shelves: Record<string, WarehouseProspect[]>;
  total: number; shown?: number; limit?: number; offset?: number;
  has_more?: boolean;
}> {
  const qs = new URLSearchParams();
  if (opts.town) qs.set('town', opts.town);
  if (opts.sector) qs.set('sector', opts.sector);
  if (opts.q) qs.set('q', opts.q);
  qs.set('limit', String(opts.limit ?? 200));
  qs.set('offset', String(opts.offset ?? 0));
  const s = qs.toString();
  return getJson<{
    shelves: Record<string, WarehouseProspect[]>;
    total: number; shown?: number; limit?: number; offset?: number;
    has_more?: boolean;
  }>(`/warehouse/shelves${s ? `?${s}` : ''}`);
}'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found - run from the project root." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "has_more?: boolean" in s:
        print("ABORT: WP1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: fetchWarehouseShelves matched %d times." % s.count(OLD))
        print("       It may already have been edited by hand.")
        return 1

    # Nothing else in this file may move. It is the file three separate
    # whole-file patches have now damaged.
    before = len(s.split("export async function")) - 1
    s = s.replace(OLD, NEW, 1)
    after = len(s.split("export async function")) - 1
    if after != before:
        print("ABORT: the number of exported functions changed (%d -> %d)."
              % (before, after))
        return 1
    # These must SURVIVE if they were there. An anchored edit cannot remove
    # them, so this is belt and braces - but it is the check that would have
    # stopped the whole-file patch that nearly deleted the Treasury Rate Desk.
    original = open(API, encoding="utf-8").read()
    for must in ("fetchRatePool", "fetchWarehouseMine", "createProspect"):
        if must in original and must not in s:
            print("ABORT: %r was in the file and is not in the result." % must)
            return 1
    print("  ok  one function changed, %d exports untouched" % after)

    if "has_more?: boolean" not in NEW or "offset" not in NEW:
        print("ABORT: the paging fields are missing.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if s.count(op) != s.count(cl):
            print("ABORT: unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: paging fields present, braces balanced")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
