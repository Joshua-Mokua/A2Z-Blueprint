#!/usr/bin/env python
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
