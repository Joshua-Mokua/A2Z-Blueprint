#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
What is actually in this HTML table? READ ONLY.

The same discipline as diag_register_pdf.py, for pages that publish a register
as a real <table> rather than a PDF. Three parsers have now been built against
imitations of a document; this one looks first.

    python scripts\\diag_html_table.py tveta_list.html
    python scripts\\diag_html_table.py tveta_list.html --table 2

Prints how many tables there are, how big each is, the header row, and the
first few rows exactly as they come out - so the reader is fitted to what is
there rather than what I imagine is there.
"""
import os
import re
import sys

TAG = re.compile(r"<[^>]+>")
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)


def _text(html):
    t = TAG.sub(" ", html or "")
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&#039;", "'")
          .replace("&quot;", '"').replace("&lt;", "<").replace("&gt;", ">"))
    return re.sub(r"\s+", " ", t).strip()


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the saved HTML file.")
        return 1
    path = sys.argv[1]
    want = 0
    if "--table" in sys.argv:
        i = sys.argv.index("--table")
        if i + 1 < len(sys.argv):
            try:
                want = int(sys.argv[i + 1]) - 1
            except ValueError:
                want = 0
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    html = open(path, encoding="utf-8", errors="ignore").read()
    tables = TABLE.findall(html)
    print("=" * 78)
    print("HTML TABLES")
    print("=" * 78)
    print("  file     %s  (%d KB)" % (os.path.basename(path), len(html) // 1024))
    print("  tables   %d\n" % len(tables))
    for n, t in enumerate(tables):
        rows = ROW.findall(t)
        widths = [len(CELL.findall(r)) for r in rows[:5]]
        print("     table %d: %d rows, first widths %s" % (n + 1, len(rows), widths))
    if not tables:
        print("\n  No <table>. The list may be rendered by script - save the")
        print("  page from the browser once it has loaded, and try again.")
        return 1

    if want >= len(tables):
        want = 0
    rows = ROW.findall(tables[want])
    print("\n" + "-" * 78)
    print("TABLE %d, FIRST ROWS" % (want + 1))
    print("-" * 78)
    for r in rows[:8]:
        cells = [_text(c) for c in CELL.findall(r)]
        if not cells:
            continue
        print("   %d cells: %s" % (len(cells),
                                   " | ".join(c[:26] for c in cells)[:150]))

    # Does it carry contacts?
    body = _text(tables[want])
    print("\n  phone-like strings : %d" % len(re.findall(r"0[17]\d{8}|\+254\d{9}", body)))
    print("  email addresses    : %d" % len(re.findall(r"[\w.\-]+@[\w.\-]+\.\w+", body)))
    print("\nSend this whole output back and the reader will be fitted to it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
