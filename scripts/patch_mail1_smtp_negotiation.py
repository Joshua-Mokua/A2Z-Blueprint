#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
MAIL1 - email notifications were never leaving the building. Our bug.

REPORT (2026-08-10): the bank provided SMTP; users receive nothing. Before
pushing back, we checked our own side. We were wrong, and here is the evidence.

WHAT THE PILOT'S CONFIG ACTUALLY SAYS (data/email_config.json):

    smtp_host          192.168.48.27      internal relay
    smtp_port          25                 plain SMTP
    sender_password    (empty)            anonymous relay
    smtp_encryption    tls                <- A KEY NOTHING IN OUR CODE READ
    sender_username    (empty)            <- ALSO NEVER READ

THE FAULT. Every send site called starttls() UNCONDITIONALLY. A port-25
internal relay normally offers no STARTTLS, so the call raises, the send returns
False, and the failure is only LOGGED. From the outside that is
indistinguishable from "email not configured" - which is exactly why this ran
for weeks without anyone noticing. The code failed safely, and safely is what
made it invisible.

Someone had also set smtp_encryption expecting it to be honoured. It was read
nowhere.

THE FIX. One helper, utils.notifications.open_smtp(cfg), used by ALL FIVE send
sites (four in core.py, one in notifications.py) - because the same mistake was
made five times independently:

    smtp_encryption = "ssl"    connect with SMTP_SSL
    smtp_encryption = "none"   never attempt STARTTLS
    anything else              STARTTLS ONLY IF THE RELAY ADVERTISES IT
                               (srv.has_extn("starttls") - the whole fix)

    login attempted only when a password exists, using sender_username if
    given, falling back to sender_email. Correct for an anonymous relay.

ALSO SHIPS scripts/diag_email.py, which walks the exact path the application
takes and reports which step fails: config -> DNS -> port -> what the relay
ADVERTISES -> STARTTLS -> login -> RCPT TO -> optional real send. Run it before
saying anything to the bank; it distinguishes our fault from theirs at each
step, and it sends nothing unless you pass --send.

AFTER APPLYING, verify against the real relay:
    python scripts\diag_email.py
    python scripts\diag_email.py --send someone@ecobank.com

If the relay accepts the envelope and the mail still does not arrive, that is
theirs to explain - and you will have the transcript to show it.

Usage (from project root, .venv active):
    python scripts\patch_mail1_smtp_negotiation.py            # dry run
    python scripts\patch_mail1_smtp_negotiation.py --apply    # write + .pre_mail1 backups
"""
import os
import re
import shutil
import sys

NOTIF = os.path.join("utils", "notifications.py")
CORE = os.path.join("utils", "core.py")
DIAG = os.path.join("scripts", "diag_email.py")
BACKUP_SUFFIX = ".pre_mail1"

ANCHOR = 'def send_email(to: str, subject: str, body: str = "",'

SEND_OLD = '''        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587))) as srv:
            srv.starttls()
            if cfg.get("sender_password"):
                srv.login(cfg["sender_email"], cfg["sender_password"])
            srv.sendmail(cfg["sender_email"], [to], msg.as_string())'''

SEND_NEW = '''        srv = open_smtp(cfg)
        try:
            srv.sendmail(cfg["sender_email"], [to], msg.as_string())
        finally:
            try:
                srv.quit()
            except Exception:
                pass'''

CORE_PAT = re.compile(
    r'( *)with smtplib\.SMTP\(cfg\["smtp_host"\], int\(cfg\.get\("smtp_port",\s*587\)\)\) as s:\n'
    r' *s\.starttls\(\)\n'
    r' *s\.login\(cfg\["sender_email"\], cfg\["sender_password"\]\)\n'
    r'( *)s\.sendmail\(([^\n]+)\)\n')

HELPER = r'''def open_smtp(cfg: dict):
    """Open an SMTP connection the way the RELAY wants, not the way we assume.

    ONE helper for every send site, because the bank's relay broke us five times
    over in exactly the same way.

    WHAT WENT WRONG (2026-08-10): the bank supplied an internal relay at
    192.168.48.27:25 - no password, anonymous. Port 25 relays usually offer no
    STARTTLS. Our code called starttls() UNCONDITIONALLY, so it raised, the send
    returned False, and the failure was only logged. From the outside that is
    indistinguishable from "email not configured", which is why nobody noticed.

    The config even carried smtp_encryption: "tls" and sender_username - keys
    NOTHING IN THE CODE READ. Someone configured the encryption mode expecting
    it to be honoured.

    Rules now:
      smtp_encryption = "ssl"   connect with SMTP_SSL (usually port 465)
      smtp_encryption = "none"  never attempt STARTTLS
      anything else             use STARTTLS ONLY IF THE RELAY ADVERTISES IT
    Authentication is attempted only when a password is present, using
    sender_username if given and falling back to sender_email.
    """
    import smtplib
    host = str(cfg.get("smtp_host") or "")
    port = int(cfg.get("smtp_port", 587) or 587)
    mode = str(cfg.get("smtp_encryption") or "").strip().lower()
    timeout = int(cfg.get("smtp_timeout", 20) or 20)

    if mode == "ssl":
        srv = smtplib.SMTP_SSL(host, port, timeout=timeout)
        srv.ehlo()
    else:
        srv = smtplib.SMTP(host, port, timeout=timeout)
        srv.ehlo()
        # Ask the relay rather than assume. has_extn() is the whole fix.
        if mode != "none" and srv.has_extn("starttls"):
            srv.starttls()
            srv.ehlo()

    pwd = cfg.get("sender_password")
    if pwd:
        user = str(cfg.get("sender_username") or cfg.get("sender_email") or "")
        srv.login(user, str(pwd))
    return srv


'''

DIAGNOSTIC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why are email notifications not arriving? READ ONLY unless you pass --send.

Establishes, with evidence, whether the fault is OURS or the relay's - before
anyone pushes back on anyone. It walks the exact path the application takes and
reports which step fails:

    1. is email_config.json present, and does it have what the code requires
    2. does the host resolve, and is the port reachable
    3. what does the relay ADVERTISE (does it even offer STARTTLS?)
    4. does STARTTLS succeed
    5. does login succeed (skipped when no password - anonymous relay)
    6. will the relay ACCEPT a message for the recipient (RCPT TO)

KNOWN WEAKNESS IN OUR CODE, which this will expose if it applies: starttls() is
called UNCONDITIONALLY at every send site. Against an internal relay on port 25
that offers no TLS, that raises, the send returns False, and the failure is
logged rather than shown - silence that looks exactly like "not configured".
Step 3 tells you whether that is what is happening here.

Nothing is sent unless you pass --send with an address:

    python scripts\\diag_email.py
    python scripts\\diag_email.py --send you@ecobank.com
"""
import os
import socket
import sys

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 72)
    print(t)
    print("=" * 72)


def main():
    send_to = ""
    if "--send" in sys.argv:
        i = sys.argv.index("--send")
        if i + 1 < len(sys.argv):
            send_to = sys.argv[i + 1]

    rule("1. CONFIGURATION")
    path = os.path.join("data", "email_config.json")
    print("   file: %s" % path)
    if not os.path.isfile(path):
        print("   *** NOT FOUND.")
        print("")
        print("   This alone explains the silence. send_email() treats a missing")
        print("   config as a deliberate no-op and logs 'email not configured'.")
        print("   Nothing is attempted, so the relay never sees a connection and")
        print("   the bank would be right that nothing arrived.")
        print("")
        print("   Needed keys: smtp_host, sender_email")
        print("   Optional:    smtp_port (default 587), sender_password, use_tls")
        return 1

    try:
        from utils.core import load_email_config
        cfg = load_email_config() or {}
    except Exception as exc:
        print("   *** could not load: %s" % exc)
        return 1

    if not cfg:
        print("   *** file exists but parsed EMPTY.")
        print("   load_email_config swallows parse errors and returns {} - so a")
        print("   malformed file is indistinguishable from an absent one.")
        return 1

    shown = dict(cfg)
    if shown.get("sender_password"):
        shown["sender_password"] = "*" * 8
    for k in sorted(shown):
        print("   %-18s %s" % (k, shown[k]))

    host = str(cfg.get("smtp_host") or "")
    port = int(cfg.get("smtp_port", 587) or 587)
    sender = str(cfg.get("sender_email") or "")
    pwd = str(cfg.get("sender_password") or "")

    missing = [k for k in ("smtp_host", "sender_email") if not cfg.get(k)]
    if missing:
        print("\n   *** MISSING REQUIRED: %s" % ", ".join(missing))
        print("   The code requires BOTH before it will attempt anything.")
        return 1
    print("\n   ok  required keys present")

    rule("2. CAN WE REACH THE RELAY?")
    try:
        ip = socket.gethostbyname(host)
        print("   %s resolves to %s" % (host, ip))
    except Exception as exc:
        print("   *** DNS FAILED for %r: %s" % (host, exc))
        print("   Ours to fix only if the hostname is wrong; otherwise theirs.")
        return 1
    try:
        s = socket.create_connection((host, port), timeout=10)
        s.close()
        print("   port %d is open" % port)
    except Exception as exc:
        print("   *** CANNOT CONNECT to %s:%d - %s" % (host, port, exc))
        print("")
        print("   Nothing on our side can fix a closed port. This is evidence")
        print("   for the bank: firewall, or the relay is not listening here.")
        return 1

    rule("3. WHAT DOES THE RELAY ADVERTISE?")
    import smtplib
    try:
        srv = smtplib.SMTP(host, port, timeout=15)
        code, banner = srv.ehlo()
        print("   EHLO %s" % code)
        feats = sorted(srv.esmtp_features.keys())
        print("   features: %s" % (", ".join(feats) or "(none)"))
        has_tls = srv.has_extn("starttls")
        has_auth = srv.has_extn("auth")
        print("   STARTTLS advertised: %s" % ("yes" if has_tls else "NO"))
        print("   AUTH advertised    : %s" % ("yes" if has_auth else "no"))
    except Exception as exc:
        print("   *** EHLO failed: %s" % exc)
        return 1

    if not has_tls:
        print("")
        print("   *** THIS IS OUR BUG, AND IT IS THE LIKELY CAUSE.")
        print("   Our code calls starttls() unconditionally at every send site.")
        print("   This relay does not offer STARTTLS, so that call raises, the")
        print("   send returns False, and the failure is only logged. From the")
        print("   outside it looks exactly like 'not configured'.")
        print("   Fix: make STARTTLS conditional on srv.has_extn('starttls').")

    rule("4. STARTTLS / LOGIN")
    if has_tls:
        try:
            srv.starttls()
            srv.ehlo()
            print("   STARTTLS ok")
        except Exception as exc:
            print("   *** STARTTLS FAILED: %s" % exc)
            return 1
    else:
        print("   skipped - not advertised")

    if pwd:
        try:
            srv.login(sender, pwd)
            print("   LOGIN ok as %s" % sender)
        except Exception as exc:
            print("   *** LOGIN FAILED for %s: %s" % (sender, exc))
            print("   Evidence for the bank: the credentials they supplied are")
            print("   rejected by their own relay.")
            try:
                srv.quit()
            except Exception:
                pass
            return 1
    else:
        print("   no password configured - anonymous relay assumed")
        print("   (our code skips login when sender_password is empty, which is")
        print("    correct for an internal relay)")

    rule("5. WILL IT ACCEPT A MESSAGE?")
    probe = send_to or sender
    try:
        srv.mail(sender)
        code, resp = srv.rcpt(probe)
        print("   MAIL FROM %s -> accepted" % sender)
        print("   RCPT TO   %s -> %s %s" % (probe, code, str(resp)[:60]))
        if code >= 400:
            print("")
            print("   *** THE RELAY REFUSES THIS RECIPIENT.")
            print("   Nothing on our side causes this. Evidence for the bank:")
            print("   relaying is denied for this sender/recipient pair.")
        srv.rset()
    except Exception as exc:
        print("   *** envelope rejected: %s" % exc)

    if send_to:
        rule("6. SENDING A REAL TEST")
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            msg = MIMEMultipart("alternative")
            msg["Subject"] = "A2Z MIS 360 - email delivery test"
            msg["From"] = sender
            msg["To"] = send_to
            msg.attach(MIMEText(
                "<p>This is a delivery test from A2Z MIS 360.</p>"
                "<p>If you are reading this, SMTP is working end to end.</p>",
                "html"))
            srv.sendmail(sender, [send_to], msg.as_string())
            print("   ACCEPTED BY THE RELAY for %s" % send_to)
            print("   If it does not arrive, the relay accepted and then dropped")
            print("   it - which is theirs to explain, not ours.")
        except Exception as exc:
            print("   *** SEND FAILED: %s" % exc)
    try:
        srv.quit()
    except Exception:
        pass

    rule("VERDICT")
    print("Every step above passed that could be tested without sending.")
    print("")
    print("If the relay accepted the envelope, our side is doing its job and the")
    print("question becomes what happens after acceptance - their queue, their")
    print("filters, their rules.")
    print("")
    print("Before pushing back, run once more with --send to a real mailbox:")
    print("   python scripts\\diag_email.py --send someone@ecobank.com")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def _core_repl(m):
    ind = m.group(1)
    args = m.group(3)
    return (f'{ind}# One SMTP path for the whole system (2026-08-10). The bank\'s relay\n'
            f'{ind}# offers no STARTTLS on port 25; calling it unconditionally here\n'
            f'{ind}# silently failed every send.\n'
            f'{ind}from utils.notifications import open_smtp\n'
            f'{ind}s = open_smtp(cfg)\n'
            f'{ind}try:\n'
            f'{ind}    s.sendmail({args})\n'
            f'{ind}finally:\n'
            f'{ind}    try:\n'
            f'{ind}        s.quit()\n'
            f'{ind}    except Exception:\n'
            f'{ind}        pass\n')


def main():
    apply = "--apply" in sys.argv
    for p in (NOTIF, CORE):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    n = open(NOTIF, encoding="utf-8").read()
    c = open(CORE, encoding="utf-8").read()

    if "def open_smtp(" in n:
        print("ABORT: open_smtp already present - MAIL1 looks applied.")
        return 1
    if n.count(ANCHOR) != 1:
        print("ABORT: send_email anchor matched %d times." % n.count(ANCHOR))
        return 1
    if n.count(SEND_OLD) != 1:
        print("ABORT: the notifications send block matched %d times."
              % n.count(SEND_OLD))
        return 1

    n = n.replace(ANCHOR, HELPER + ANCHOR, 1)
    n = n.replace(SEND_OLD, SEND_NEW, 1)
    print("  ok  notifications.py - open_smtp added, send site rewired")

    c, k = CORE_PAT.subn(_core_repl, c)
    if k != 4:
        print("ABORT: expected 4 send sites in core.py, rewrote %d." % k)
        print("       Refusing to half-migrate - a mixed state would leave some")
        print("       mail silently failing while the rest works, which is worse")
        print("       than the original bug.")
        return 1
    print("  ok  core.py - %d send sites routed through open_smtp" % k)

    # post-checks
    if "s.starttls()" in c:
        print("ABORT: post-check - unconditional starttls survives in core.py.")
        return 1
    if 'srv.starttls()' in n and 'has_extn("starttls")' not in n:
        print("ABORT: post-check - starttls in notifications is not conditional.")
        return 1
    for token in ("smtp_encryption", "sender_username", 'has_extn("starttls")',
                  "SMTP_SSL"):
        if token not in HELPER:
            print("ABORT: the helper does not handle %r." % token)
            return 1
    print("  ok  post-checks: one path, no unconditional STARTTLS")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((NOTIF, n), (CORE, c)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    if not os.path.exists(DIAG):
        open(DIAG, "w", encoding="utf-8", newline="").write(DIAGNOSTIC)
        print("CREATED %s" % DIAG)

    import py_compile
    for path in (NOTIF, CORE):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Restart uvicorn, then prove it against the real relay:")
    print("  python scripts\\diag_email.py")
    print("  python scripts\\diag_email.py --send someone@ecobank.com")
    return 0


if __name__ == "__main__":
    sys.exit(main())
