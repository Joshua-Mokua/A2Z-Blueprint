#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DV1 - a document is served as what it is, so it can be viewed.

FROM THE BANK (2026-09-03): "on the view documents, I have noted that some
attachments, mostly Word documents, are returning an error on view."

EVERY DOCUMENT WAS SERVED IDENTICALLY:

    media_type="application/octet-stream"
    Content-Disposition: attachment

"application/octet-stream" means "a stream of bytes, I will not say what kind".
The browser has nothing to work with, so nothing previews - not the PDFs, not
the images, not the scans. And "attachment" tells it to download rather than
display, which is the opposite of View.

WHAT THIS CHANGES: the type is taken from the filename, and previewable things
are served inline.

    .pdf                  application/pdf                 inline
    .png .jpg .gif .webp  image/*                         inline
    .txt .csv             text/plain, text/csv            inline
    .doc .docx            application/msword, ...         attachment
    .xls .xlsx            application/vnd.ms-excel, ...   attachment
    anything else         octet-stream                    attachment

A BROWSER CANNOT PREVIEW A WORD DOCUMENT. No media type changes that - there
is no renderer for .docx in Chrome or Edge. What this fixes for Word is that it
now downloads cleanly, with the right type, instead of erroring in a viewer
that was never going to display it.

The honest position is that "View" means "open the PDF" and "download the Word
file", and the file name in the list already tells an officer which they are
about to get.

THE FILENAME IS QUOTED AND STRIPPED. A filename containing a quote or a newline
could break out of the Content-Disposition header, which is a header-injection
hole as well as a broken download.

Usage (from project root, .venv active):
    python scripts\patch_dv1_documents_are_viewable.py            # dry run
    python scripts\patch_dv1_documents_are_viewable.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_dv1"

OLD = '''    return StreamingResponse(_io_docup.BytesIO(data),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{meta.get("filename","file")}"'})'''

NEW = '''    # ── SERVE IT AS WHAT IT IS ──────────────────────────────────────────────
    # Everything used to go out as application/octet-stream with
    # Content-Disposition: attachment - "a stream of bytes, I will not say what
    # kind, and download it". Nothing previewed, and the viewer errored on the
    # Word files it was never going to be able to render.
    #
    # A browser cannot preview a .docx whatever we send. What changes for Word
    # is that it downloads cleanly with the right type instead of failing in a
    # viewer. What changes for PDFs and images is that they now display.
    _fname = str(meta.get("filename", "") or "file")
    _ext = os.path.splitext(_fname)[1].lower()
    _INLINE = {
        ".pdf":  "application/pdf",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif":  "image/gif",
        ".webp": "image/webp",
        ".bmp":  "image/bmp",
        ".txt":  "text/plain; charset=utf-8",
        ".csv":  "text/csv; charset=utf-8",
    }
    _DOWNLOAD = {
        ".doc":  "application/msword",
        ".docx": ("application/vnd.openxmlformats-officedocument"
                  ".wordprocessingml.document"),
        ".xls":  "application/vnd.ms-excel",
        ".xlsx": ("application/vnd.openxmlformats-officedocument"
                  ".spreadsheetml.sheet"),
        ".ppt":  "application/vnd.ms-powerpoint",
        ".pptx": ("application/vnd.openxmlformats-officedocument"
                  ".presentationml.presentation"),
        ".zip":  "application/zip",
    }
    if _ext in _INLINE:
        _type, _disp = _INLINE[_ext], "inline"
    else:
        _type = _DOWNLOAD.get(_ext, "application/octet-stream")
        _disp = "attachment"

    # A filename with a quote or a newline in it could break out of the header.
    # That is a header-injection hole as well as a broken download.
    _safe = _fname.replace('"', "").replace("\\r", "").replace("\\n", "").strip()
    if not _safe:
        _safe = "document%s" % (_ext or "")

    _audit("API_DEAL_DOC_SERVED", user,
           f"deal={deal_id}|doc={doc_name}|type={_type}|{_disp}")
    return StreamingResponse(_io_docup.BytesIO(data),
        media_type=_type,
        headers={"Content-Disposition": f'{_disp}; filename="{_safe}"'})'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "SERVE IT AS WHAT IT IS" in s:
        print("ABORT: DV1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the document response matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  documents are served as their real type")

    if 'replace(\'"\', "")' not in NEW:
        print("ABORT: the filename is not sanitised - a quote in it would")
        print("       break out of the Content-Disposition header.")
        return 1
    if '".docx"' not in NEW or '".pdf"' not in NEW:
        print("ABORT: the types the bank actually attaches are missing.")
        return 1
    if 'inline' not in NEW or 'attachment' not in NEW:
        print("ABORT: everything would be served the same way again.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: inline vs attachment, filename sanitised")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + BACKUP_SUFFIX)
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. A PDF now opens in the tab; a Word file")
    print("downloads with the right type instead of erroring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
