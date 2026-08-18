#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
What does pdfplumber ACTUALLY see in this PDF? READ ONLY. Diagnostic.

WHY THIS EXISTS. The extractor has been wrong three times because it was built
against PDFs I constructed to imitate the gazette, not the gazette itself. Each
guess looked right on the imitation and produced fragments on the real file.

This prints the real structure so the parser can be built from evidence:
ruled tables, word coordinates, the column gaps, and the first rows as the
extractor would see them.

Send the output back and the parser gets built to fit THIS document rather than
another guess.

    python scripts\\diag_register_pdf.py sasra_2026.pdf
    python scripts\\diag_register_pdf.py sasra_2026.pdf --page 3
"""
import os
import sys


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: python scripts\\diag_register_pdf.py <file.pdf> [--page N]")
        return 1
    path = args[0]
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1
    page_no = 2
    if "--page" in sys.argv:
        i = sys.argv.index("--page")
        if i + 1 < len(sys.argv):
            try:
                page_no = int(sys.argv[i + 1])
            except ValueError:
                pass

    try:
        import pdfplumber
    except ImportError:
        print("ABORT: pip install pdfplumber --break-system-packages")
        return 1

    with pdfplumber.open(path) as pdf:
        print("=" * 78)
        print("PDF STRUCTURE")
        print("=" * 78)
        print("  pages   %d" % len(pdf.pages))
        if page_no > len(pdf.pages):
            page_no = 1
        page = pdf.pages[page_no - 1]
        print("  showing page %d  (size %.0f x %.0f)"
              % (page_no, page.width, page.height))

        # 1. Are there ruled tables?
        tables = page.extract_tables() or []
        print("\n  RULED TABLES FOUND: %d" % len(tables))
        if tables:
            t = tables[0]
            print("     first table: %d rows x %d cols" % (len(t), len(t[0]) if t else 0))
            for row in t[:4]:
                print("       %s" % [str(c)[:22] if c else "" for c in row])

        # 2. Lines - if the document draws any, extract_tables can use them.
        print("\n  LINES: %d horizontal, %d vertical"
              % (len(page.horizontal_edges or []), len(page.vertical_edges or [])))

        # 3. Word positions - the basis for rebuilding a borderless table.
        words = page.extract_words() or []
        print("\n  WORDS: %d" % len(words))
        if words:
            xs = sorted({round(float(w["x0"])) for w in words})
            print("     distinct x-starts: %d" % len(xs))
            print("     leftmost 14: %s" % xs[:14])

            # Column starts show up as x-positions many words share.
            import collections
            cnt = collections.Counter(round(float(w["x0"]) / 2) * 2 for w in words)
            common = [x for x, n in cnt.most_common(10) if n >= 5]
            print("     x-positions used by 5+ words (likely columns): %s"
                  % sorted(common)[:10])

        # 4. What the row grouping produces - the extractor's actual input.
        print("\n  ROWS REBUILT FROM WORD POSITIONS (first 8):")
        lines = {}
        for w in words:
            lines.setdefault(round(float(w["top"]) / 3.0), []).append(w)
        shown = 0
        for key in sorted(lines):
            ws = sorted(lines[key], key=lambda x: float(x["x0"]))
            cells, cur, prev_end = [], [], None
            for w in ws:
                x0, x1 = float(w["x0"]), float(w["x1"])
                if prev_end is not None and (x0 - prev_end) > 11:
                    cells.append(" ".join(cur))
                    cur = []
                cur.append(w["text"])
                prev_end = x1
            if cur:
                cells.append(" ".join(cur))
            if not any(c.strip() for c in cells):
                continue
            shown += 1
            print("     [%d cells] %s"
                  % (len(cells), " | ".join(c[:26] for c in cells[:5])))
            if shown >= 8:
                break

        # 5. Raw text, for comparison.
        print("\n  RAW TEXT (first 8 lines):")
        for ln in (page.extract_text() or "").split("\n")[:8]:
            print("     %s" % ln[:96])

    print("\n" + "=" * 78)
    print("Send this whole output back. The parser will be built to fit what is")
    print("actually here - three versions have now been built against imitations")
    print("of this document rather than the document.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
