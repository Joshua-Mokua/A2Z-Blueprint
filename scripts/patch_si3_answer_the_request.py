#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The person asked for input gets somewhere to answer.

SI1 added the endpoints and SI2 the asking. The answering half has nothing:
a committee member sees the question on the journey and no way to reply, so
they answer in a corridor and the file records nothing.

Adds a panel at the top of the case, shown only to somebody who has an open
request on it.

    python scripts/patch_si3_answer_the_request.py            # dry run
    python scripts/patch_si3_answer_the_request.py --apply
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "LmsApplicationDetail.tsx")
API = os.path.join("frontend", "web", "src", "lib", "api.ts")

API_FN = '''
/** Answer a request for input. Recorded on the journey; it decides nothing. */
export async function respondToInputRequest(
  appId: string,
  body: { answer: string; stance?: 'supports' | 'opposes' | 'commented' },
): Promise<{ application_id: string; input: string }> {
  return postJson<{ application_id: string; input: string }, typeof body>(
    `/lms/applications/${encodeURIComponent(appId)}/input-response`, body);
}
'''

PANEL = '''
// ─── ANSWERING A REQUEST FOR INPUT ────────────────────────────────────────────
// Credit risk can ask a named person what they think without returning the
// case. The question landed on the journey and there was nowhere to reply, so
// the answer happened in a corridor and the file recorded nothing.
//
// Shown only to somebody who has an open request on this case.
function InputRequestPanel({ application, onDone }:
    { application: { id: string; input_requests?: unknown[] }; onDone: () => Promise<void> | void }) {
  const { user } = useRole();
  const { toast } = useToast();
  const [answer, setAnswer] = useState('');
  const [stance, setStance] = useState<'supports' | 'opposes' | 'commented'>('supports');
  const [busy, setBusy] = useState(false);

  const me = String(user?.staff_code ?? '');
  const reqs = (application.input_requests ?? []) as Array<Record<string, unknown>>;
  const mine = reqs.filter((r) => !r.answered && String(r.to ?? '') === me);
  if (!me || mine.length === 0) return null;
  const q = mine[mine.length - 1];

  async function send() {
    if (answer.trim().length < 5) return;
    setBusy(true);
    try {
      await respondToInputRequest(String(application.id),
                                  { answer: answer.trim(), stance });
      toast({ tone: 'success', message: 'Your input is on the case.' });
      setAnswer('');
      await onDone();
    } catch (e) {
      toast({ tone: 'error',
              message: e instanceof Error ? e.message : 'Could not record that.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 rounded-lg border border-[#0097A7] bg-[#F0FBFC] p-4">
      <div className="text-sm font-semibold text-[#003D57]">
        {String(q.asked_by_name ?? 'Credit risk')} has asked for your input
      </div>
      <p className="mt-1 text-sm text-gray-800">{String(q.question ?? '')}</p>
      <p className="mt-1 text-xs text-gray-500">
        This is recorded on the case. It does not approve or decline anything —
        credit risk still decides.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div>
          <label className="block text-xs font-medium text-gray-700">Your view</label>
          <select className="mt-1 rounded-lg border px-3 py-2 text-sm" value={stance}
                  onChange={(e) => setStance(e.target.value as typeof stance)}>
            <option value="supports">I support it</option>
            <option value="opposes">I do not support it</option>
            <option value="commented">Comment only</option>
          </select>
        </div>
        <div className="min-w-[22rem] flex-1">
          <label className="block text-xs font-medium text-gray-700">Why</label>
          <input className="mt-1 w-full rounded-lg border px-3 py-2 text-sm"
                 value={answer} onChange={(e) => setAnswer(e.target.value)}
                 placeholder="What you want on the record" />
        </div>
        <button type="button" disabled={answer.trim().length < 5 || busy}
                onClick={() => void send()}
                className={`rounded-lg px-4 py-2 text-sm font-medium text-white ${
                  answer.trim().length >= 5 && !busy ? 'bg-[#0097A7]' : 'bg-gray-300'}`}>
          {busy ? 'Recording…' : 'Record my input'}
        </button>
      </div>
    </div>
  );
}

'''

ANCHOR = "        {/* ─────────── ACTION: Record Decision (if can_record_decision) ─────────── */}"
MOUNT = '''        {/* Shown only to somebody who has been asked for input on this case. */}
        <InputRequestPanel
          application={application as unknown as { id: string; input_requests?: unknown[] }}
          onDone={reload} />

'''


def main():
    apply = "--apply" in sys.argv
    for f in (PAGE, API):
        if not os.path.isfile(f):
            print("%s not found." % f)
            return 1

    p = open(PAGE, encoding="utf-8").read()
    a = open(API, encoding="utf-8").read()
    if "InputRequestPanel" in p:
        print("Already applied.")
        return 1
    if p.count(ANCHOR) != 1:
        print("The decision panel anchor matched %d times." % p.count(ANCHOR))
        return 1

    # The page must have something to refresh with.
    import re
    # The name must be a function IN SCOPE on this page, not merely a prop
    # name passed to a child. On LmsApplicationDetail the reloader is
    # `refetch`, destructured from the fetch hook - the original check matched
    # `onDone={refetch}` and would have emitted onDone={onDone}, undefined here.
    reloader = ""
    for cand in ("refetch", "reload", "refresh"):
        if re.search(r"(const|let|var|function)\s[^\n]*\b%s\b" % cand, p):
            reloader = cand
            break
    if not reloader:
        print("No reload function found on this page - the panel would not")
        print("refresh after answering. Not applying.")
        return 1

    if "respondToInputRequest" not in a:
        a = a.rstrip() + "\n" + API_FN

    mount = MOUNT.replace("onDone={reload}", "onDone={%s}" % reloader)
    p = p.replace(ANCHOR, mount + ANCHOR, 1)

    m = re.search(r"^function ActionPanelDecision", p, re.M)
    if not m:
        m = re.search(r"^function \w+Panel", p, re.M)
    if not m:
        print("Could not find a component to place the panel beside.")
        return 1
    p = p[:m.start()] + PANEL + p[m.start():]

    im = re.search(r"^import \{ ([A-Za-z]+),", p, re.M)
    if not im:
        print("Could not find the api import list.")
        return 1
    p = p.replace(im.group(0),
                  "import { respondToInputRequest,\n  %s," % im.group(1), 1)

    if "respondToInputRequest" not in p.split("function ")[0]:
        print("respondToInputRequest is used but not imported.")
        return 1
    if "String(r.to ?? '') === me" not in p:
        print("Anybody could answer somebody else's request.")
        return 1
    if p.count("{") != p.count("}") or p.count("(") != p.count(")"):
        print("Braces unbalanced.")
        return 1
    print("The panel shows only to whoever has an open request, and refreshes")
    print("through %r." % reloader)

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Run tsc - it will catch anything this assumed about the page.")
        return 0

    for path, src in ((API, a), (PAGE, p)):
        shutil.copy2(path, path + ".pre_si3")
        open(path, "w", encoding="utf-8", newline="").write(src)
        print("Applied %s" % path)
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
