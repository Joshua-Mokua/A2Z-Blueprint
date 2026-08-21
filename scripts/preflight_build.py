#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Every reason a release BUILD would fail, in one run. READ ONLY.

RULING (2026-08-21), after five aborts in a row: "aren't we supposed to
wholistically review before we release, to seal all loopholes that would make
us not spend a whole hour for a release."

Yes. The builder ABORTS AT THE FIRST PROBLEM, which is correct for a build - it
must not stack patches onto a half-written file. But it means a release with
four faults takes four builds to find them, and each costs a branch, a replay
and fifteen minutes.

This runs the same checks and reports ALL of them at once.

    python scripts\preflight_build.py

NOT to be confused with preflight_release.py, which asks a different question -
whether the PILOT will work once it lands (committees staffed, logins valid,
quorum reachable). This asks whether the release will BUILD at all.

    1. the working tree is clean          the builder switches branches
    2. you are not on a release branch    a stranded build leaves you there
    3. every patcher is placed            in the chain, or named as excluded
    4. every chain patcher is on disk     a missing file aborts the replay
    5. the whole chain replays cleanly    against a real copy of alex-dev
    6. the result compiles
    7. authentication is untouched        the pilot's AD login must not move
    8. nothing of the bank's travels      no config of theirs may be staged

Step 5 is the slow one, and it is the one that would have caught four of the
five aborts.
"""
import os
import shutil
import subprocess
import sys
import tempfile

FAIL = []


def sh(*a, **kw):
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    # WINDOWS DEFAULTS TO cp1252 AND THE SOURCE IS UTF-8. Without this, reading
    # a file with a box-drawing character in a comment raises
    # UnicodeDecodeError inside a reader thread - and the caller sees empty
    # output rather than an error. That made the auth check report five files
    # as MOVED when nothing had moved at all.
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(list(a), **kw)


def sh_bytes(*a):
    """Raw bytes, no decoding. For comparing file contents, where a decode is
    not just unnecessary but actively dangerous - a failed decode looks like a
    difference."""
    return subprocess.run(list(a), capture_output=True).stdout


def note(ok, title, detail=""):
    print("  %-5s %-54s %s" % ("ok" if ok else "FAIL", title, detail[:18]))
    if not ok:
        FAIL.append(title)


def main():
    if not os.path.isfile(os.path.join("scripts", "build_alex_release.py")):
        print("ABORT: run this from the project root.")
        return 1

    print("=" * 82)
    print("WOULD THIS RELEASE BUILD?")
    print("=" * 82)

    branch = sh("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    dirty = [l for l in sh("git", "status", "--porcelain").stdout.split("\n")
             if l.strip() and not l.startswith("??")]
    note(not dirty, "the working tree has no uncommitted tracked changes",
         "%d modified" % len(dirty) if dirty else "")
    for l in dirty[:6]:
        print("             %s" % l.strip()[:62])
    note(not branch.startswith("release/"),
         "you are not standing on a release branch", branch)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "b", os.path.join("scripts", "build_alex_release.py"))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        print("\nABORT: the builder will not import: %s" % str(exc)[:60])
        return 1
    chain = list(getattr(mod, "CHAIN", []))
    excluded = set(getattr(mod, "NOT_FOR_RELEASE", set()))
    on_disk = {f[:-3] for f in os.listdir("scripts")
               if f.startswith("patch_") and f.endswith(".py")}
    # ── THE SAME RULE THE BUILDER USES ──────────────────────────────────────
    # A patcher that edits build_alex_release.py cannot be replayed onto the
    # pilot - the pilot has no release builder. The builder learned this; this
    # check did not, so it went on reporting them as unplaced.
    #
    # A rule enforced in one place and not the other is not a rule, it is a
    # coincidence. Both read the same fact from the same files.
    edits_builder = set()
    for f in os.listdir("scripts"):
        if not (f.startswith("patch_") and f.endswith(".py")):
            continue
        try:
            if "build_alex_release" in open(os.path.join("scripts", f),
                                            encoding="utf-8",
                                            errors="ignore").read():
                edits_builder.add(f[:-3])
        except OSError:
            pass
    unplaced = sorted(on_disk - set(chain) - excluded - edits_builder)
    if edits_builder:
        print("  note  %d patcher(s) edit the release builder and are excluded"
              % len(edits_builder))
        print("        automatically - they cannot reach the pilot.")
    note(not unplaced, "every patcher is in the chain or named as excluded",
         "%d unplaced" % len(unplaced) if unplaced else "")
    for p in unplaced:
        print("             %s" % p)

    missing = [p for p in chain
               if not os.path.isfile(os.path.join("scripts", "%s.py" % p))]
    note(not missing, "every patcher in the chain is on disk",
         "%d missing" % len(missing) if missing else "")
    for p in missing[:6]:
        print("             %s" % p)

    if FAIL:
        print("\n" + "=" * 82)
        print("STOPPING - fix these before the slow replay is worth running")
        print("=" * 82)
        for f in FAIL:
            print("  * %s" % f)
        return 1

    print("\n  replaying %d patchers against a copy of origin/alex-dev ..."
          % len(chain))
    tmp = tempfile.mkdtemp(prefix="preflight_build_")
    applied = 0
    try:
        arch = subprocess.run(["git", "archive", "origin/alex-dev"],
                              stdout=subprocess.PIPE)
        p = subprocess.Popen(["tar", "-x", "-C", tmp], stdin=subprocess.PIPE)
        p.communicate(arch.stdout)
        sdir = os.path.join(tmp, "scripts")
        os.makedirs(sdir, exist_ok=True)
        for f in os.listdir("scripts"):
            if f.endswith(".py"):
                shutil.copy2(os.path.join("scripts", f), os.path.join(sdir, f))

        failed = []
        for name in chain:
            r = sh(sys.executable, os.path.join("scripts", "%s.py" % name),
                   "--apply", cwd=tmp)
            out = (r.stdout or "") + (r.stderr or "")
            if "APPLIED" in out or "CREATED" in out:
                applied += 1
            elif "looks applied" in out or "already" in out:
                pass
            else:
                why = next((l.strip() for l in out.split("\n")
                            if "ABORT" in l or "Error" in l), "")
                failed.append((name, why[:58]))

        note(not failed, "every patcher replays cleanly onto alex-dev",
             "%d applied" % applied if not failed else "%d failed" % len(failed))
        for name, why in failed[:8]:
            print("             %-40s %s" % (name, why))

        pyf = [os.path.join(tmp, f) for f in
               ("utils/api.py", "utils/api_lms_routes.py",
                "utils/api_cbs_routes.py", "utils/api_lms_scope.py")
               if os.path.isfile(os.path.join(tmp, f))]
        r = sh(sys.executable, "-m", "py_compile", *pyf) if pyf else None
        note(r is not None and r.returncode == 0,
             "the replayed python compiles",
             (r.stderr or "").strip()[:18] if r else "nothing to compile")

        # COMPARE BYTES, NOT TEXT. A file is the same or it is not; decoding
        # it first only creates ways for identical files to look different.
        moved = []
        for f in getattr(mod, "DELTA", []):
            a = sh_bytes("git", "show", "origin/alex-dev:%s" % f)
            q = os.path.join(tmp, f)
            b = open(q, "rb").read() if os.path.isfile(q) else b""
            # Line endings differ between a git blob and a checked-out file on
            # Windows, and that is not a change anybody made.
            if a and b and a.replace(b"\r\n", b"\n") != b.replace(b"\r\n", b"\n"):
                moved.append(f)
        note(not moved, "the pilot's authentication files are untouched",
             "%d moved" % len(moved) if moved else "")
        for f in moved[:5]:
            print("             %s" % f)

        theirs = []
        for f in ("data/lms_config.json", "data/users.json",
                  "data/pipeline_settings.json", "data/org_config.json"):
            a = sh_bytes("git", "show", "origin/alex-dev:%s" % f)
            if not a:
                continue
            q = os.path.join(tmp, f)
            if os.path.isfile(q):
                b = open(q, "rb").read()
                if a.replace(b"\r\n", b"\n") != b.replace(b"\r\n", b"\n"):
                    theirs.append(os.path.basename(f))
        note(not theirs, "no configuration of the bank's would be overwritten",
             ", ".join(theirs)[:18])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\n" + "=" * 82)
    if FAIL:
        print("THIS RELEASE WOULD FAIL")
        print("=" * 82)
        for f in FAIL:
            print("  * %s" % f)
        print("\n  Fix ALL of the above, then re-run this. One pass beats five")
        print("  builds - which is exactly why this exists.")
        return 1
    print("THIS RELEASE WOULD BUILD")
    print("=" * 82)
    print("  %d patchers replay cleanly, the result compiles, authentication" % applied)
    print("  is intact, and nothing of the bank's travels.")
    print("\n   python scripts\\build_alex_release.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
