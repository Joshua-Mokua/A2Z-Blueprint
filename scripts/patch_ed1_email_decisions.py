#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Decide a case by email reply, from anywhere off the LAN.

Two changes:

  1. send_email honours reply_to and sends real attachments. It built a
     message with no Reply-To, so every reply went to noreply and vanished;
     and it accepted an attachments argument it never used.

  2. utils/email_decisions.py is copied in - the module that sends a case
     for decision and reads the replies.

Copy email_decisions.py into utils/ first.

    python scripts/patch_ed1_email_decisions.py            # dry run
    python scripts/patch_ed1_email_decisions.py --apply
"""
import os
import re
import shutil
import sys

MOD = os.path.join("utils", "notifications.py")
EDM = os.path.join("utils", "email_decisions.py")

OLD = '''        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = _from_header(cfg)
        msg["To"]      = to
        msg.attach(MIMEText(body or subject, "html"))'''

NEW = '''        # "mixed" so real attachments can ride along; "alternative" was for text
        # and html only, and silently dropped anything else.
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"]    = _from_header(cfg)
        msg["To"]      = to
        # Where a reply goes. Without this every reply went to noreply and was
        # never read - which is what a decision-by-email needs to work.
        _reply_to = str(kwargs.get("reply_to") or cfg.get("reply_to") or "").strip()
        if _reply_to:
            msg["Reply-To"] = _reply_to
        _is_html = "<" in (body or "") and ">" in (body or "")
        msg.attach(MIMEText(body or subject, "html" if _is_html else "plain"))
        # Attachments, if any were given. The parameter existed and was ignored.
        for _p in (attachments or []):
            try:
                from email.mime.base import MIMEBase
                from email import encoders as _enc
                with open(_p, "rb") as _fh:
                    _part = MIMEBase("application", "octet-stream")
                    _part.set_payload(_fh.read())
                _enc.encode_base64(_part)
                _part.add_header("Content-Disposition",
                                 "attachment; filename=\\"%s\\""
                                 % os.path.basename(_p))
                msg.attach(_part)
            except Exception:
                pass'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1
    if not os.path.isfile(EDM):
        print("%s is not there. Copy email_decisions.py into utils\\\\ first." % EDM)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if 'msg["Reply-To"]' in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("send_email's message build matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    # os at module level. The first "import smtplib" is INSIDE open_smtp, so
    # replacing it put a bare import inside a function - unexpected indent.
    head = s.split("\ndef ", 1)[0]
    if not re.search(r"^import os\b", head, re.M):
        m = re.search(r"^(from __future__ import [^\n]+\n)", s, re.M)
        if m:
            s = s[:m.end()] + "import os\n" + s[m.end():]
        else:
            m = re.search(r"^(import |from )", s, re.M)
            s = (s[:m.start()] + "import os\n" + s[m.start():]) if m else "import os\n" + s

    if "Reply-To" not in s or "MIMEBase" not in s:
        print("Reply-To or attachments not wired.")
        return 1
    import ast
    try:
        ast.parse(s)
        ast.parse(open(EDM, encoding="utf-8").read())
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("send_email honours reply_to and attaches files.")
    print("utils/email_decisions.py is in place.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("\nThe bank must add to data/email_config.json:")
        print('   "imap_host", "imap_port", "imap_user", "imap_password",')
        print('   "reply_to"  - a mailbox the system can READ.')
        print("Without it, sending works and nothing ever comes back.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_ed1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    py_compile.compile(MOD, doraise=True)
    py_compile.compile(EDM, doraise=True)
    print("Both compile.")
    print("\nThen:  python scripts/send_case_by_email.py --app LMS00035 --to KE1219 --dry-run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
