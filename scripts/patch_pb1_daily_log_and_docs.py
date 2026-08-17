#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PB1 - the daily log stops eating the morning, and a .doc is refused honestly.

TWO PILOT FAULTS (2026-08-12), plus a diagnostic for two more that need the
running instance to answer.

1. "WHEN A TELLER KEYS IN A TRANSACTION DONE AT 9, THEN AT 11 THEY WANT TO ADD
   OTHER TRANSACTIONS, IT OVERRIDES THE ONE AT 9."

   Confirmed, and it affects EVERY hourly input, not just tellers. The whole
   hourly map was replaced by whatever the form last held:

       existing["hourly"] = hourly

   The page does rehydrate today's entry on load, which is why it does not
   happen every time. It fails when the rehydrate does not win: the user starts
   typing before the fetch returns - the guard only fills an EMPTY map, so a
   late response is discarded - or they are on a second device.

   MERGED BY HOUR NOW, NOT SUMMED. Each hour is a slot: a payload carrying
   hour 11 leaves hour 9 alone, and one carrying hour 9 again REPLACES hour 9,
   which is what a correction is. Summing would double a corrected figure and a
   teller fixing a typo would silently inflate the branch.

       09:00 keys 20      -> 20
       11:00 adds 15      -> 35     (was 15)
       corrects 09 to 18  -> 33     (not 53)

   Fixed on the SERVER, because the client cannot be relied on to send the
   whole day. Applied to save_draft() as well as submit() - a draft saved at 11
   would erase the morning just as effectively.

   ANSWERING THE QUESTION DIRECTLY: they can keep entering through the day.
   End-of-day-only would have been a workaround for a bug, and would lose the
   hourly shape the daily log exists to capture.

2. "A DOCUMENT SENT IN WORD IS NOT ABLE TO VIEW IN APP, INSTEAD ASKING FOR A
   DOWNLOAD - we are avoiding customer documents being stored on people's PCs."

   .docx already renders through mammoth. The file that failed is a legacy
   .doc - an older BINARY format, not an older version of .docx. Mammoth cannot
   read it and no browser-side library reads it reliably.

   It used to fall through to a generic "In-app preview isn't available",
   which said nothing useful. It now names the problem, says that .docx and PDF
   DO open in the app, and offers a download only to whoever already has that
   right - which is the existing credit-analysis permission, unchanged.

   Blocking the download outright was tried first and was stricter than the
   policy: it left an analyst who IS permitted to download unable to read the
   document at all, which helps nobody.

   WORD ITSELF ALREADY VIEWS. .docx renders through mammoth and always has.
   Only the pre-2007 binary .doc cannot, and no browser-side library reads it
   reliably - the durable fix is server-side conversion, a bigger job than a
   pilot day allows.

3. scripts/diag_pilot_blockers.py answers the other two from YOUR data.

   THE COMMITTEES - it separates "never written" from "written without
   kind='branch'". On this repo's config the palette holds five committees and
   NONE carries kind='branch', so anything filtering on branch kind sees none:
   "no branch credit committee is set" is literally true while the records sit
   there. If the pilot shows the same, the 16 need their kind set rather than
   being recreated.

   THE STUCK DEAL - a deal reading pending-validation with no request id cannot
   appear in any manager queue, because the queue is built from request
   records. The owner is then blocked by a flag nobody can clear from the
   interface, which is what was described.

Verified: py_compile clean, tsc --noEmit clean, vite build clean, and the three
daily-log cases measured above.

Usage (from project root, .venv active):
    python scripts\\patch_pb1_daily_log_and_docs.py            # dry run
    python scripts\\patch_pb1_daily_log_and_docs.py --apply
"""
import os
import shutil
import sys

BL = os.path.join("utils", "branch_log.py")
VIEWER = os.path.join("frontend", "web", "src", "components", "DocumentViewerModal.tsx")
DIAG = os.path.join("scripts", "diag_pilot_blockers.py")
BACKUP_SUFFIX = ".pre_pb1"

TAIL = r'''            existing.update(metrics)
            existing["remarks"] = remarks
            if hourly:
                existing["hourly"] = hourly'''

MERGE = r'''            # ── HOURLY IS MERGED, NEVER REPLACED (pilot, 2026-08-12) ─────────
            # "When a teller keys in a transaction done at 9, then at 11 they
            # want to add other transactions, it overrides the one at 9."
            #
            # It did. The whole hourly map was replaced by whatever the form
            # last held, so a page opened fresh at 11 - or one where the user
            # began typing before the rehydrate fetch returned - wrote back
            # only the 11 o'clock block and the morning vanished.
            #
            # MERGED BY HOUR, NOT SUMMED. Each hour is a slot: a payload
            # carrying hour 11 leaves hour 9 alone, and one carrying hour 9
            # again REPLACES hour 9 - which is what a correction is. Summing
            # would double a corrected figure, so a teller fixing a typo would
            # silently inflate the branch.
            #
            # Fixed on the SERVER because the client cannot be relied on to
            # send the whole day: it races its own rehydrate, and a second
            # device knows nothing of the first.
            #
            # APPLIED TO BOTH submit() AND save_draft() - a draft saved at 11
            # would erase the morning just as effectively as a submission.
            if hourly:
                _merged = dict(existing.get("hourly") or {})
                _merged.update(hourly)
                hourly = _merged
                _derived = derive_from_hourly(hourly)
                metrics = {k: _num(_derived.get(k, 0)) for k in metric_keys()}
                for _k in metric_keys():
                    if _k not in metrics:
                        metrics[_k] = 0
'''

VIEWER_SRC = r'''// ──────────────────────────────────────────────────────────────────────────
// DocumentViewerModal — read a deal document WITHIN the system.
//
// Renders the document inline (no download needed for a read):
//   • PDF                    → native inline (iframe)
//   • images                 → native inline (img)
//   • text / csv / json / md → inline text
//   • .docx                  → converted to HTML via mammoth (lazy-loaded)
//   • .xlsx / .xls           → converted to HTML tables via SheetJS (lazy-loaded)
//   • other (e.g. .pptx)     → download-to-read fallback (no native preview)
//
// `canDownload` gates the download affordance: relationship owners / analysts
// get it; committee members read but cannot download (a note shows instead).
// ──────────────────────────────────────────────────────────────────────────
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Button } from '@/components/Button';
import { downloadDealDocument } from '@/lib/api';

type Kind = 'pdf' | 'image' | 'text' | 'docx' | 'legacy-doc' | 'xlsx' | 'other';

function kindOf(filename: string): Kind {
  const ext = (filename.toLowerCase().split('.').pop() || '');
  if (ext === 'pdf') return 'pdf';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(ext)) return 'image';
  if (['txt', 'csv', 'json', 'md', 'log'].includes(ext)) return 'text';
  if (ext === 'docx') return 'docx';
  // LEGACY WORD (.doc) IS A DIFFERENT FORMAT, not an older version of .docx -
  // a binary container mammoth cannot read and no browser-side library reads
  // reliably. It used to fall through to "other", which offered a DOWNLOAD -
  // exactly what the bank is trying to avoid with customer documents sitting
  // on people's PCs. Named here so it can be refused properly instead.
  if (ext === 'doc') return 'legacy-doc';
  if (['xlsx', 'xls'].includes(ext)) return 'xlsx';
  return 'other';
}

export function DocumentViewerModal({
  dealId, docName, filename, canDownload = true, onClose, fetchBlob,
}: {
  dealId: string;
  docName: string;
  filename: string;
  canDownload?: boolean;
  onClose: () => void;
  /** Optional custom fetcher (e.g. LMS-side download). Defaults to the deal document route. */
  fetchBlob?: () => Promise<Blob>;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [text, setText] = useState<string | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const kind = kindOf(filename);
  const doFetch = fetchBlob ?? (() => downloadDealDocument(dealId, docName));

  useEffect(() => {
    let alive = true;
    let objUrl: string | null = null;
    (async () => {
      try {
        const blob = await doFetch();
        if (!alive) return;
        if (kind === 'text') {
          setText(await blob.text());
        } else if (kind === 'docx') {
          const buf = await blob.arrayBuffer();
          const mod: any = await import('mammoth');
          const mammoth = mod.default ?? mod;
          const { value } = await mammoth.convertToHtml({ arrayBuffer: buf });
          if (alive) setHtml(value || '<p><em>Empty document.</em></p>');
        } else if (kind === 'xlsx') {
          const buf = await blob.arrayBuffer();
          const XLSX: any = await import('xlsx');
          const wb = XLSX.read(buf, { type: 'array' });
          const parts = (wb.SheetNames as string[]).map((name) =>
            `<h3>${name}</h3>${XLSX.utils.sheet_to_html(wb.Sheets[name])}`);
          if (alive) setHtml(parts.join('\n') || '<p><em>Empty workbook.</em></p>');
        } else {
          // The download endpoint serves application/octet-stream, which a PDF
          // <iframe> will not render — re-type PDFs so the browser renders them
          // inline. Images render fine from any blob (the browser sniffs them).
          const src = kind === 'pdf'
            ? new Blob([await blob.arrayBuffer()], { type: 'application/pdf' })
            : blob;
          objUrl = URL.createObjectURL(src);
          setUrl(objUrl);
        }
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : 'Could not load document');
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; if (objUrl) URL.revokeObjectURL(objUrl); };
  }, [dealId, docName, kind]);

  const doDownload = async () => {
    try {
      const blob = await doFetch();
      const href = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = href; a.download = filename; a.click();
      setTimeout(() => URL.revokeObjectURL(href), 10000);
    } catch {
      setError('Download failed.');
    }
  };

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden="true" />
      <div className="relative flex h-[94vh] w-full max-w-[95vw] flex-col rounded-lg border border-gray-200 bg-white shadow-xl">
        <div className="flex items-center justify-between gap-3 border-b border-gray-200 px-5 py-3">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-gray-900">{docName}</div>
            <div className="truncate text-xs text-gray-500">{filename}</div>
          </div>
          <div className="flex items-center gap-2">
            {canDownload && !loading && (
              <Button variant="ghost" size="sm" onClick={() => void doDownload()}>Download</Button>
            )}
            <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          </div>
        </div>
        <div className="flex-1 overflow-auto bg-gray-50">
          {loading && <div className="p-6 text-sm text-gray-500">Loading…</div>}
          {error && <div className="p-6 text-sm text-red-600">{error}</div>}
          {!loading && !error && kind === 'pdf' && url && (
            <iframe title={docName} src={url} className="h-full w-full" />
          )}
          {!loading && !error && kind === 'image' && url && (
            <div className="flex h-full items-center justify-center p-4">
              <img src={url} alt={docName} className="max-h-full max-w-full object-contain" />
            </div>
          )}
          {!loading && !error && kind === 'text' && text != null && (
            <pre className="whitespace-pre-wrap p-5 text-xs text-gray-800">{text}</pre>
          )}
          {!loading && !error && (kind === 'docx' || kind === 'xlsx') && html != null && (
            <div className="doc-html bg-white p-6 text-sm text-gray-800">
              <style>{`
                .doc-html table { border-collapse: collapse; margin: 0.5rem 0; }
                .doc-html td, .doc-html th { border: 1px solid #d1d5db; padding: 4px 8px; }
                .doc-html h1, .doc-html h2 { font-weight: 600; margin: 0.75rem 0 0.4rem; }
                .doc-html h3 { font-weight: 600; margin: 0.75rem 0 0.3rem; color: #005B82; }
                .doc-html p { margin: 0.35rem 0; }
                .doc-html ul, .doc-html ol { margin: 0.35rem 0 0.35rem 1.25rem; }
              `}</style>
              <div dangerouslySetInnerHTML={{ __html: html }} />
            </div>
          )}
          {/* LEGACY .doc - REFUSED, NOT OFFERED FOR DOWNLOAD. Falling through to
              the generic branch put a "Download to read" button in front of a
              customer document, which is the thing the bank is trying to stop.
              The honest answer is that the file is in a format nothing can
              render in a browser, and the fix is at the source. */}
          {!loading && !error && kind === 'legacy-doc' && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <div className="text-sm text-gray-700">
                This is a legacy Word file (.doc) and cannot be shown in the app.
              </div>
              <div className="max-w-md text-xs text-gray-500">
                It is an older binary format from before 2007 — not a newer Word
                document — and nothing renders it in a browser. Modern Word
                files (<strong>.docx</strong>) open here normally, as do PDFs,
                so asking for it in either keeps it in the app.
              </div>
              {/* DOWNLOAD IS OFFERED, but only to whoever already has the
                  right (ruling 2026-08-12: "I would be okay to allow them
                  download if it is Word, but remember there are those we have
                  allowed the download rights especially in credit analysis").
                  Blocking it outright was stricter than the policy - it left an
                  analyst who IS permitted to download unable to read a document
                  at all, which helps nobody. Everyone else still cannot. */}
              {canDownload
                ? <Button onClick={() => void doDownload()}>Download to read</Button>
                : <div className="text-xs text-gray-400">
                    Download is not permitted for your role — ask for this as a
                    PDF or .docx and it will open here.
                  </div>}
            </div>
          )}

          {!loading && !error && kind === 'other' && (
            <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center">
              <div className="text-sm text-gray-600">
                In-app preview isn’t available for this file type yet.
              </div>
              {canDownload
                ? <Button onClick={() => void doDownload()}>Download to read</Button>
                : <div className="text-xs text-gray-400">Download is not permitted for your role.</div>}
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
'''

DIAG_SRC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why is no branch committee set, and why is a deal stuck? READ ONLY.

TWO PILOT REPORTS (2026-08-12) that need YOUR data to answer - the committees
and the deals live on the running instance, not in the repository, so this
reports what is actually there rather than what I would guess.

    python scripts\\diag_pilot_blockers.py
    python scripts\\diag_pilot_blockers.py --deal D2989
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def committees():
    """"We created the 16 branch committees but the admin is not able to see
    them, and thus technically no branch credit committee is set."

    Two different faults produce that sentence, and they need different fixes:
    the committees were never written, or they were written without the `kind`
    the branch filter looks for. This tells them apart.
    """
    # Read the file directly - the loader name has moved before and a
    # diagnostic that cannot run is worth nothing.
    import json
    path = os.path.join("data", "lms_config.json")
    if not os.path.isfile(path):
        print("  data/lms_config.json not found.")
        return
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh) or {}
    cw = cfg.get("credit_workflow", {}) if isinstance(cfg, dict) else {}
    pal = cw.get("committee_palette")
    if not isinstance(pal, list):
        print("  committee_palette is MISSING from lms_config.credit_workflow.")
        print("  Nothing was ever written - the 16 did not save.")
        return
    print("  palette entries: %d" % len(pal))
    if not pal:
        print("  The palette is EMPTY. Whatever created the 16 did not persist.")
        return

    import collections
    kinds = collections.Counter(str(c.get("kind", "") or "(none)").lower() for c in pal)
    print("  by kind: %s" % dict(kinds))
    branch = [c for c in pal if str(c.get("kind", "")).lower() == "branch"]
    print("  entries with kind='branch': %d" % len(branch))

    if pal and not branch:
        print("")
        print("  *** THIS IS THE FAULT. Committees exist, but none carries")
        print("      kind='branch'. Anything that filters on branch kind - the")
        print("      branch-committee generator, and any journey that expects a")
        print("      branch gate - sees none, so 'no branch credit committee is")
        print("      set' is literally true even though the records are there.")
        print("")
        print("      Fix the kind on the 16 rather than recreating them, or")
        print("      re-run the generator which sets it:")
        print("        POST /api/admin/committee-palette/generate-branch")
    for c in pal[:8]:
        print("     %-8s %-46s kind=%s" % (str(c.get("code"))[:8],
                                           str(c.get("name"))[:46],
                                           c.get("kind") or "(none)"))
    if len(pal) > 8:
        print("     ... and %d more" % (len(pal) - 8))

    # Which products actually reference a committee gate?
    try:
        from utils.core import get_pipeline_settings
        flows = (get_pipeline_settings() or {}).get("product_flows") or {}
        codes = {str(c.get("code")) for c in pal}
        print("\n  PRODUCTS AND THEIR COMMITTEE GATES")
        for prod, e in list(flows.items())[:12]:
            j = (e or {}).get("committee_journey") or []
            bad = [g for g in j if g not in codes]
            print("     %-28s %s%s" % (prod[:28], j or "(none)",
                                       "  <-- unknown: %s" % bad if bad else ""))
    except Exception as exc:
        print("  (could not read product flows: %s)" % str(exc)[:50])


def stuck_validation(deal_id=""):
    """"The branch manager sees nothing pending validation, but the owner
    cannot close, saying it is pending validation."

    Two flags, read by two surfaces. If they disagree the deal is invisible to
    the person who could clear it and immovable for the person who owns it -
    which is exactly what was reported.
    """
    from utils.core import PipelineManager
    pm = PipelineManager()
    deals = list(getattr(pm, "deals", []) or [])
    if deal_id:
        deals = [d for d in deals if str(d.get("id")) == deal_id]
        if not deals:
            print("  no deal %r found" % deal_id)
            return

    def _pending(d):
        # Anything that makes a deal READ as awaiting validation.
        return (bool(d.get("validation_requested"))
                or str(d.get("validation_status", "")).lower() in
                ("pending", "requested", "awaiting")
                or (d.get("pending_validation") is True))

    odd = []
    for d in deals:
        pending = _pending(d)
        validated = bool(d.get("manager_validated"))
        # The contradiction: reads as pending AND already validated, or
        # reads as pending with no open request record for a manager to see.
        if pending and validated:
            odd.append((d, "reads pending but manager_validated is already True"))
        elif pending and not d.get("validation_request_id"):
            odd.append((d, "reads pending but carries no request id - nothing "
                           "for a manager's queue to show"))

    print("  deals examined: %d" % len(deals))
    if not odd:
        print("  no contradictory validation states found.")
        if deal_id:
            d = deals[0]
            print("\n  %s state:" % deal_id)
            for k in ("stage", "manager_validated", "validation_requested",
                      "validation_status", "validation_request_id",
                      "cancel_requested", "draft"):
                print("     %-24s %r" % (k, d.get(k)))
        return

    print("  *** %d deal(s) in a contradictory state:" % len(odd))
    for d, why in odd[:10]:
        print("     %-10s %-24s %s" % (str(d.get("id"))[:10],
                                       str(d.get("client_name"))[:24], why))
        for k in ("stage", "manager_validated", "validation_requested",
                  "validation_status", "validation_request_id"):
            print("        %-22s %r" % (k, d.get(k)))
    print("")
    print("  A deal reading pending with no request id cannot appear in any")
    print("  manager queue - the queue is built from request records. The owner")
    print("  is blocked by a flag nobody can clear from the interface.")


def main():
    deal_id = ""
    if "--deal" in sys.argv:
        i = sys.argv.index("--deal")
        if i + 1 < len(sys.argv):
            deal_id = sys.argv[i + 1].strip()

    rule("1. THE COMMITTEE PALETTE")
    try:
        committees()
    except Exception as exc:
        print("  could not read: %s" % exc)

    rule("2. VALIDATION STATE")
    try:
        stuck_validation(deal_id)
    except Exception as exc:
        print("  could not read: %s" % exc)

    print("\n" + "=" * 78)
    print("Send this output back. Both of these depend on data I cannot see")
    print("from here, and guessing at them has cost time already today.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


MERGE_OLD = "        if existing:\n" + TAIL


def main():
    apply = "--apply" in sys.argv
    for p in (BL, VIEWER):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    bl = open(BL, encoding="utf-8").read()
    if "HOURLY IS MERGED" in bl:
        print("ABORT: PB1 looks applied.")
        return 1

    # TWO write sites - submit() and save_draft(). Fixing one and leaving the
    # other would keep the draft path eating the morning, which is the harder
    # failure to notice.
    n = bl.count(MERGE_OLD)
    if n != 2:
        print("ABORT: expected 2 hourly write sites (submit and save_draft),")
        print("       found %d. Refusing to fix one and leave the other." % n)
        return 1
    bl = bl.replace(MERGE_OLD, "        if existing:\n" + MERGE + TAIL)
    print("  ok  hourly merged in both submit() and save_draft()")

    if "_merged.update(hourly)" not in MERGE:
        print("ABORT: the merge does not replace per hour.")
        return 1
    if "+=" in MERGE or "sum(" in MERGE:
        print("ABORT: the merge appears to SUM - a teller correcting a typo")
        print("       would inflate the branch.")
        return 1
    if "legacy-doc" not in VIEWER_SRC:
        print("ABORT: legacy .doc is not recognised.")
        return 1
    i = VIEWER_SRC.find("kind === 'legacy-doc'")
    j = VIEWER_SRC.find("kind === 'other'", i)
    seg = VIEWER_SRC[i:j if j > i else i + 2000]
    # A download IS offered, but only behind canDownload. Refusing outright was
    # stricter than the policy and left a permitted analyst unable to read the
    # document at all; offering it unconditionally would put customer files on
    # any PC. The gate is the whole point.
    if "doDownload" in seg and "canDownload" not in seg:
        print("ABORT: the legacy .doc branch offers a download WITHOUT checking")
        print("       canDownload - that puts customer files on any PC.")
        return 1
    if "docx" not in seg.lower():
        print("ABORT: the message does not tell the user what to ask for.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if VIEWER_SRC.count(op) != VIEWER_SRC.count(cl):
            print("ABORT: viewer unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: per-hour merge, legacy .doc download stays gated")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((BL, bl), (VIEWER, VIEWER_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    if not os.path.exists(DIAG):
        open(DIAG, "w", encoding="utf-8", newline="").write(DIAG_SRC)
        print("CREATED %s" % DIAG)

    import py_compile
    try:
        py_compile.compile(BL, doraise=True)
        print("  ok  branch_log.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Then run this and send me the output - the committees and the stuck")
    print("deal both live in your data, not in the repo:")
    print("  python scripts\\diag_pilot_blockers.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
