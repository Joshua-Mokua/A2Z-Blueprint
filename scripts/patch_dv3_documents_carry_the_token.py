#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DV3 - opening a document sends the bearer token.

FROM THE BANK (2026-09-04), from the browser's own address bar:

    https://10.32.1.79/api/pipeline/deals/D0678/documents/...
    {"detail":"Missing or malformed Authorization header"}

THE VIEW LINK IS A PLAIN <a href>. Every API call needs
`Authorization: Bearer <token>`, the token lives in a module variable that
AuthProvider sets on login - and a browser link cannot carry it. Clicking View
navigates the tab straight to the endpoint with no header at all, so the server
refuses before it ever looks at the document.

DV1 WAS A DIFFERENT FAULT AND BOTH WERE REAL. DV1 made the server send the
right media type, so a PDF displays instead of downloading as an unnamed blob.
This one is why nothing reached the server in the first place.

WHAT THIS CHANGES: View fetches the document WITH the header, turns the
response into a blob URL, and opens that.

    a PDF or an image     opens in a new tab, as before but now it arrives
    a Word or Excel file  downloads with its real filename
    a refusal             shows the server's message instead of a raw JSON
                          page in a tab

THE BLOB URL IS REVOKED. A blob left in memory holds the whole file for as long
as the page lives, and a document list opened a few times would keep every one
of them.

Usage (from project root, .venv active):
    python scripts\patch_dv3_documents_carry_the_token.py            # dry run
    python scripts\patch_dv3_documents_carry_the_token.py --apply
"""
import os
import shutil
import sys

CLIENT = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")

CLIENT_ANCHOR = "export function setCurrentToken(token: string | null): void {"

CLIENT_BLOCK = '''/** Open a document that lives behind the bearer token.
 *
 *  The View link used to be a plain <a href> to the endpoint. A browser link
 *  carries no Authorization header - the token is a module variable, not a
 *  cookie - so the tab landed on
 *
 *      {"detail":"Missing or malformed Authorization header"}
 *
 *  This fetches WITH the header and opens the result, so the server sees an
 *  authenticated request and answers with the document.
 *
 *  The blob URL is revoked afterwards: a blob holds the whole file in memory
 *  for as long as the page lives, and a document list opened a few times would
 *  keep every one of them.
 */
export async function openProtectedFile(path: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (_currentToken) headers['Authorization'] = `Bearer ${_currentToken}`;
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = String(j.detail);
    } catch { /* not JSON - keep the status */ }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const disp = res.headers.get('Content-Disposition') || '';
  const inline = disp.toLowerCase().startsWith('inline');
  if (inline) {
    window.open(url, '_blank', 'noopener,noreferrer');
  } else {
    // A Word or Excel file cannot be previewed by a browser whatever we send,
    // so it is downloaded under its real name rather than opened into a tab
    // that would only offer to save it anyway.
    const m = /filename="([^"]+)"/.exec(disp);
    const a = document.createElement('a');
    a.href = url;
    a.download = m ? m[1] : path.split('/').pop() || 'document';
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  // Long enough for the tab or the download to take hold.
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

'''

PAGE_OLD = '''              <a
                href={`/api/pipeline/deals/${encodeURIComponent(dealId)}/documents/${encodeURIComponent(n)}`}
                target="_blank" rel="noopener noreferrer"
                className="font-medium text-brand-primary hover:underline"
              >
                View
              </a>'''

PAGE_NEW = '''              {/* NOT an <a href>. A browser link carries no Authorization
                  header, so clicking View landed the tab on
                  {"detail":"Missing or malformed Authorization header"}.
                  openProtectedFile fetches with the token and opens the
                  result. */}
              <button
                type="button"
                onClick={() => {
                  void openProtectedFile(
                    `/pipeline/deals/${encodeURIComponent(dealId)}`
                    + `/documents/${encodeURIComponent(n)}`,
                  ).catch((e) => toast({
                    tone: 'danger',
                    message: `Could not open ${n}: ${e instanceof Error ? e.message : 'unknown error'}`,
                  }));
                }}
                className="font-medium text-brand-primary hover:underline"
              >
                View
              </button>'''


def main():
    apply = "--apply" in sys.argv
    for f in (CLIENT, PAGE):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    c = open(CLIENT, encoding="utf-8").read()
    p = open(PAGE, encoding="utf-8").read()
    if "openProtectedFile" in c:
        print("ABORT: DV3 looks applied.")
        return 1
    if c.count(CLIENT_ANCHOR) != 1:
        print("ABORT: the token setter matched %d times." % c.count(CLIENT_ANCHOR))
        return 1
    if p.count(PAGE_OLD) != 1:
        print("ABORT: the View link matched %d times." % p.count(PAGE_OLD))
        return 1
    if "_currentToken" not in c or "API_BASE" not in c:
        print("ABORT: the token variable or the API base is not where expected.")
        return 1

    c = c.replace(CLIENT_ANCHOR, CLIENT_BLOCK + CLIENT_ANCHOR, 1)
    p = p.replace(PAGE_OLD, PAGE_NEW, 1)

    # AND IMPORT IT. tsc did not complain on the first attempt because one of
    # the two occurrences was inside a comment - a clean typecheck that proves
    # nothing is worse than a failing one.
    IMP = "import { fetchPipelineDealDetail,"
    if "openProtectedFile" not in p.split("export")[0] and IMP in p:
        p = p.replace(IMP, "import { openProtectedFile,\n  fetchPipelineDealDetail,", 1)
    print("  ok  View fetches with the token instead of navigating")

    if "href={`/api/pipeline/deals/" in p:
        print("ABORT: a plain link to the endpoint survives - it would fail the")
        print("       same way.")
        return 1
    if "revokeObjectURL" not in CLIENT_BLOCK:
        print("ABORT: the blob is never released and would hold every opened")
        print("       document in memory.")
        return 1
    if "toast(" not in PAGE_NEW:
        print("ABORT: a refusal would be silent.")
        return 1
    if p.count("{") != p.count("}") or p.count("(") != p.count(")"):
        print("ABORT: the page's braces are unbalanced.")
        return 1
    # The import must be REAL, not a mention in a comment.
    _head = p.split("export function")[0]
    if "openProtectedFile" not in _head:
        print("ABORT: openProtectedFile is used but never imported. tsc may")
        print("       still pass if the only other mention is in a comment.")
        return 1
    print("  ok  post-checks: no plain link, blob released, imported, reported")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        print("\nNOTE: openProtectedFile must be imported in the page. tsc")
        print("      will say so if the import list needs it.")
        return 0

    for path, src in ((CLIENT, c), (PAGE, p)):
        shutil.copy2(path, path + ".pre_dv3")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("APPLIED %s" % path)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
