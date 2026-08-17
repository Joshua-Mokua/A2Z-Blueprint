#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DOC1 - who attaches each document, submit pending the rest, and a truthful button.

THREE RULINGS FROM THE PILOT (2026-08-12), plus an audit of the whole journey.

1. "THERE ARE DOCUMENTS SUBMITTED BY THE OWNER, DOCUMENTS ATTACHED BY THE
   DEPARTMENT ANALYST, AND DOCUMENTS ATTACHED BY THE CREDIT ANALYST. It was
   noted that the documents required are all to be attached at the
   documentation stage, which is not the case."

   A required document was a bare NAME, which silently meant "the deal owner
   produces this" - including for papers only an analyst can write. The owner
   was blocked by documents they had no way of obtaining.

   A document is now {name, attached_by, mandatory}. The admin sets who owes
   each one from a dropdown. PLAIN STRINGS STILL WORK and mean "owner", because
   every product is configured as a list of strings today and breaking those to
   add a field would take the pilot down to gain nothing.

2. "ALL DOCUMENTS MAY NOT BE READY AT THE SAME TIME, and delaying the analysis
   due to a document that may not really be standing in the way has been picked
   up as a hard condition we need to relook into."

   The gate was ALL-OR-NOTHING. Now:

       ONLY THE OWNER'S DOCUMENTS are considered at submission. An analyst's
       paper was never the owner's to produce.

       SUBMISSION PROCEEDS with documents outstanding, and what is outstanding
       is RECORDED ON THE DEAL - so the analyst sees what is still coming and
       the owner can be chased. Waved through would be worse than blocked;
       recorded is neither.

       MANDATORY documents still block, and that is the point: the bank now
       chooses which few genuinely cannot be worked without, instead of every
       document blocking by default.

3. "THE SUBMIT BUTTON IS STILL READING SUBMIT TO ANALYSIS, which should instead
   be submitting to the next stage - which in a branch case is Branch Credit
   Committee, then the Department Credit Analyst, and so on."

   THE ADVANCE WAS ALWAYS RIGHT - one stage, config-driven, per product. Only
   the LABEL lied, and a button naming a step three transitions away teaches
   people the wrong shape of their own process. GET .../next-step returns the
   real next stage, so the button says "Submit to Branch Credit Committee".

THE JOURNEY AUDIT (scripts/audit_deal_journey.py) walks capture to disbursement
and reports blocks and warnings. It found exactly the two faults above and
nothing else: the flow resolves end to end, every advance is config-driven, an
application is created and linked back, and the credit-admin and disbursement
stages all exist.

It also taught me two things about auditing, both now fixed in it:

    A WINDOW SIZED IN BYTES silently truncates when the endpoint grows, and
    then reports what fell past the cut as MISSING. It claimed no application
    was created, minutes after I had read the line that creates one.

    MATCHING A PHRASE ANYWHERE IN A FILE matches the comment explaining why the
    phrase was wrong. It reported the button fix as the button fault.

    And its first run claimed eight stages were rejected by an allow-list the
    advance endpoint never consults - a catastrophic-sounding finding that was
    not true. settings["stages"] is dead config from the old generic sales
    pipeline; it is now reported as such, once, as a warning.

THE FRONTEND EDITS ARE ANCHORED, NOT WHOLE FILES. PipelineDealDetail.tsx is on
the deployment delta list and Alex has his own additions in it - a read-only
"attached documents" view for oversight roles. Shipping the whole file would
erase that. Four anchored edits apply on top of whatever he has.

(Checked while there: his copy also still abbreviates KES to K/M/B, which the
FMT ruling of 2026-08-09 deliberately removed. That travels to him with this
release; his document view stays.)

Verified: py_compile clean, tsc --noEmit clean, vite build clean, audit green.

Usage (from project root, .venv active):
    python scripts\patch_doc1_document_roles.py            # dry run
    python scripts\patch_doc1_document_roles.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
ADMIN = os.path.join("frontend", "web", "src", "pages", "AdminConfig.tsx")
DETAIL = os.path.join("frontend", "web", "src", "pages", "PipelineDealDetail.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
AUDIT = os.path.join("scripts", "audit_deal_journey.py")
BACKUP_SUFFIX = ".pre_doc1"

MODEL_ANCHOR = "def _product_document_config(deal: dict) -> tuple:"
EP_ANCHOR = '@app.post("/api/pipeline/deals/{deal_id}/submit-to-credit")'

VALID_OLD = '''    rd = entry.get("required_documents")
    if rd is not None:
        if not isinstance(rd, list) or any(not isinstance(x, str) for x in rd):
            return False, "required_documents must be a list of strings"'''
VALID_NEW = '''    rd = entry.get("required_documents")
    if rd is not None:
        if not isinstance(rd, list):
            return False, "required_documents must be a list"
        for x in rd:
            # A plain string is still valid and means "owner" - every existing
            # configuration is a list of strings, and breaking those to add a
            # field would take the pilot down to gain nothing.
            if isinstance(x, str):
                continue
            if not isinstance(x, dict) or not str(x.get("name") or "").strip():
                return False, ("required_documents entries must be a name, or "
                               "{name, attached_by}")
            by = str(x.get("attached_by") or "owner").lower()
            if by not in {"owner", "department_analyst", "credit_analyst",
                          "credit_admin", "customer"}:
                return False, "unknown attached_by %r" % by
            if "mandatory" in x and not isinstance(x.get("mandatory"), bool):
                return False, "mandatory must be true or false"'''

GATE_OLD = '''    provided = list(payload.documents_provided or [])
    missing = [d for d in state["required"] if d not in provided]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit to credit — missing documents: "
                   + ", ".join(missing),
        )'''

TS_ANCHOR = "export async function fetchCreditChecklist("
TS_NEW = '''export interface NextStep {
  deal_id: string; current_stage: string; next_stage: string;
  submit_label: string; flow: string[];
  documents: { name: string; attached_by: string; mandatory: boolean }[];
  by_attacher: { attacher: string; have: string[]; outstanding: string[] }[];
  owner_outstanding: string[]; blocking: string[]; can_submit: boolean;
  attachers: { key: string; label: string }[];
}
export async function fetchNextStep(dealId: string): Promise<NextStep> {
  return getJson<NextStep>(`/pipeline/deals/${encodeURIComponent(dealId)}/next-step`);
}
'''

# ── ANCHORED EDITS to the deal detail page. Alex has his own additions in this
# file; replacing it wholesale would erase them.
DETAIL_EDITS = [
    ("import { fetchPipelineDealDetail, fetchCreditChecklist,",
     "import { fetchPipelineDealDetail, fetchCreditChecklist, fetchNextStep, type NextStep,"),
    ("  const [checklist,  setChecklist]  = useState<CreditChecklistResponse | null>(null);",
     """  const [checklist,  setChecklist]  = useState<CreditChecklistResponse | null>(null);
  // What the next stage actually is, and who owes which document. Fetched
  // rather than assumed - the flow is config-driven and per product, so the
  // page cannot know it without asking.
  const [nextStep, setNextStep] = useState<NextStep | null>(null);"""),
    ("""    fetchCreditChecklist(deal.id)
      .then((c) => {""",
     """    void fetchNextStep(deal.id).then((n) => { if (alive) setNextStep(n); })
      .catch(() => { /* label falls back to "Submit to next stage" */ });
    fetchCreditChecklist(deal.id)
      .then((c) => {"""),
    ("""            <Button
              onClick={() => void onSubmit()}
              loading={submitting}
              disabled={missing.length > 0 || !checklist.can_submit}
            >
              Submit to Credit Analysis
            </Button>""",
     """            {/* THE BUTTON NAMES THE REAL DESTINATION (ruling 2026-08-12). The
                advance was always right - one stage, config-driven - but the
                label named a step three transitions away, which teaches people
                the wrong shape of their own process.

                And it is no longer disabled by outstanding paperwork: only
                MANDATORY documents block now, so the deal can move while the
                rest is still being gathered. */}
            <Button
              onClick={() => void onSubmit()}
              loading={submitting}
              disabled={(nextStep?.blocking?.length ?? 0) > 0 || !checklist.can_submit}
            >
              {nextStep?.submit_label ?? 'Submit to next stage'}
            </Button>"""),
]

MODEL = r'''# ── WHO ATTACHES A DOCUMENT ─────────────────────────────────────────────────
# RULING (2026-08-12): "there are documents submitted by the owner, documents
# attached by the department analyst, and documents attached by the credit
# analyst. It was noted that the documents required are all to be attached at
# the documentation stage, which is not the case."
#
# A flat list of names cannot express that, so every document fell to the deal
# owner - including the ones only an analyst can produce. The owner was being
# blocked from submitting by papers they had no way of obtaining.
#
# A document is now {"name": ..., "attached_by": ...}. PLAIN STRINGS STILL WORK
# and mean "owner", because every existing configuration is a list of strings
# and a migration that breaks the pilot to add a field is not worth it.
DOC_ATTACHERS = [
    {"key": "owner", "label": "Deal owner / RM"},
    {"key": "department_analyst", "label": "Department analyst"},
    {"key": "credit_analyst", "label": "Credit analyst"},
    {"key": "credit_admin", "label": "Credit admin"},
    {"key": "customer", "label": "Customer"},
]
_DOC_ATTACHER_KEYS = {d["key"] for d in DOC_ATTACHERS}


def _normalise_document(doc) -> dict:
    """One shape for a required document, whichever way it was configured."""
    if isinstance(doc, dict):
        name = str(doc.get("name") or doc.get("document") or "").strip()
        by = str(doc.get("attached_by") or "owner").strip().lower()
    else:
        name, by = str(doc or "").strip(), "owner"
    if by not in _DOC_ATTACHER_KEYS:
        by = "owner"
    # MANDATORY is opt-in, and deliberately so. Before today every document
    # blocked; making them all mandatory by default would reinstate exactly the
    # hard condition the pilot asked us to remove. The bank now marks the few
    # that genuinely cannot be worked without.
    mand = bool(doc.get("mandatory")) if isinstance(doc, dict) else False
    return {"name": name, "attached_by": by, "mandatory": mand}


def _documents_for(deal: dict, attached_by: str = "") -> list:
    """Required documents, optionally narrowed to one attacher.

    `attached_by="owner"` answers the only question the submit gate should ask:
    what is OUTSTANDING FROM THE PERSON SUBMITTING. An analyst's paper is not
    the owner's to produce, and blocking on it stops work for no benefit.
    """
    docs = [_normalise_document(d) for d in _get_required_documents_for_deal(deal)]
    docs = [d for d in docs if d["name"]]
    if attached_by:
        docs = [d for d in docs if d["attached_by"] == attached_by]
    return docs


'''

ENDPOINT = r'''@app.get("/api/pipeline/deals/{deal_id}/next-step")
def pipeline_next_step(deal_id: str, user: dict = Depends(get_current_user)):
    """What happens when this deal is submitted, and what is still owed.

    RULING (2026-08-12): "the submit button is still reading submit to analysis,
    which should instead be submitting to the next stage - which in a branch
    case is submit to Branch Credit Committee, then after the committee
    recommends, submit to the Department Credit Analyst, and so on."

    The advance itself was always right - one stage, config-driven. The LABEL
    was wrong, and a button that names a step three transitions away teaches
    people the wrong shape of their own process.

    Returns the real next stage so the button can say it, plus the documents
    split BY WHO OWES THEM - because "8 documents outstanding" is not
    actionable when six of them belong to an analyst who has not started.
    """
    pm = PipelineManager()
    deal = pm.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="No such deal.")

    cur = str(deal.get("stage") or "")
    flow = _stage_flow_for(deal.get("product_type") or deal.get("product", "")) or []
    nxt = ""
    if cur in flow:
        i = flow.index(cur)
        if i + 1 < len(flow):
            nxt = flow[i + 1]

    docs = _documents_for(deal)
    provided = set(str(d) for d in (deal.get("documents_provided") or []))
    by_who = {}
    for d in docs:
        e = by_who.setdefault(d["attached_by"], {"attacher": d["attached_by"],
                                                 "have": [], "outstanding": []})
        (e["have"] if d["name"] in provided else e["outstanding"]).append(d["name"])

    owner_out = [d["name"] for d in docs
                 if d["attached_by"] == "owner" and d["name"] not in provided]
    blocking = [d["name"] for d in docs
                if d.get("mandatory") and d["name"] not in provided
                and d["attached_by"] == "owner"]

    return {
        "deal_id": deal_id,
        "current_stage": cur,
        "next_stage": nxt,
        # What the button should say. Naming the destination is the whole point.
        "submit_label": ("Submit to %s" % nxt) if nxt else "Submit",
        "flow": flow,
        "documents": docs,
        "by_attacher": sorted(by_who.values(), key=lambda x: x["attacher"]),
        "owner_outstanding": owner_out,
        "blocking": blocking,
        "can_submit": not blocking,
        "attachers": DOC_ATTACHERS,
    }


'''

SOFT_GATE = r'''    # ── SUBMIT PENDING OTHER DOCUMENTS ──────────────────────────────────────
    # RULING (2026-08-12): "all documents may not be ready at the same time, and
    # delaying the analysis due to a document that may not really be standing in
    # the way of analysis has been picked up as a hard condition we need to
    # relook into."
    #
    # The gate was ALL-OR-NOTHING: one outstanding paper stopped the deal, even
    # when the analysis could have started without it. Three changes:
    #
    #   1. ONLY THE OWNER'S DOCUMENTS ARE EVEN CONSIDERED. An analyst's paper
    #      was never the owner's to produce, and blocking on it stopped work
    #      for nobody's benefit.
    #
    #   2. SUBMISSION IS ALLOWED WITH DOCUMENTS OUTSTANDING, and what is
    #      outstanding is RECORDED ON THE DEAL rather than forgotten - so the
    #      analyst can see what is still coming and the owner can be chased.
    #
    #   3. ATTACHING STAYS OPEN after submission, which is what makes this
    #      honest rather than a way of skipping paperwork.
    #
    # A document may still be marked MANDATORY, and those DO block - some
    # papers genuinely cannot be worked without. The difference is that the
    # bank now chooses which, instead of every document being treated as
    # blocking by default.
    provided = list(payload.documents_provided or [])
    owner_docs = _documents_for(deal, attached_by="owner")
    owner_names = [d["name"] for d in owner_docs] or list(state["required"])
    outstanding = [d for d in owner_names if d not in provided]

    blocking = []
    for d in owner_docs:
        if d["name"] in outstanding and bool(d.get("mandatory")):
            blocking.append(d["name"])
    if blocking:
        raise HTTPException(
            status_code=400,
            detail="Cannot submit — these documents are mandatory before "
                   "analysis can begin: " + ", ".join(blocking),
        )

    if outstanding:
        # Recorded, not waved through. The next person to open this deal sees
        # exactly what is still owed and by whom.
        try:
            pm.update_deal(deal_id, {
                "documents_outstanding": outstanding,
                "documents_outstanding_at": datetime.now().isoformat(timespec="seconds"),
            }, str(user.get("username", "") or ""))
        except Exception as _exc:
            logger.warning("could not record outstanding documents: %s", _exc)
'''

ADMIN_SRC = r'''// Admin → Configuration (Batch 1b).
//
// CEO / MD / Director surface for editing pipeline + credit reference config
// that today lives in Streamlit: deal-create required fields, customer segments
// (Ecobank display names + per-type options), the product catalogue, the MOU
// register, and CBK sectors. Each panel reads its slice from /api/pipeline/stages
// and PATCHes via /api/admin/pipeline-config (gated server-side by
// require_config_admin). Currency/FX has its own dedicated page (/fx-rates).
//
// The page is also UX-gated to the executive tier; the server is the real
// authority (a non-exec PATCH returns 403).

import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { PageHeader } from '@/components/PageHeader';
import { AdminTabs } from '@/components/AdminTabs';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { Badge } from '@/components/Badge';
import { useToast } from '@/components/Toast';
import { useRole } from '@/hooks/useRole';
import {
  fetchPipelineConfig,
  updatePipelineConfig,
  upsertMou,
  upsertProductFlow,
  fetchDocumentCatalog,
  addDocumentType,
  fetchCommitteePalette,
  type CommitteeDef,
  getCommitteeTiers,
  saveCommitteeTiers,
  getAdminBranches,
  saveAdminBranches,
  fetchSlaConfig,
  saveSlaConfig,
  type AdminConfigPatch,
  type CommitteeTier,
  type AdminBranch,
  type SlaConfig,
} from '@/lib/api';
import type { PipelineConfig, ProductFlow, DealCategoryConfig } from '@/types/pipeline';

type Mou = { id: string; title: string; partner_name?: string; active?: boolean };
type ClientType = { key: string; label: string; field: 'mou' | 'sector' };

// Deal-create fields that can be toggled mandatory. Keys must match what the
// create form + backend _required_fields understand.
const REQUIRABLE_FIELDS: { key: string; label: string }[] = [
  { key: 'client_name', label: 'Client name' },
  { key: 'product_type', label: 'Product type' },
  { key: 'deal_value', label: 'Deal value' },
  { key: 'stage', label: 'Initial stage' },
  { key: 'segment', label: 'Segment' },
  { key: 'currency', label: 'Currency' },
  { key: 'relationship_status', label: 'Relationship status (NTB / Existing)' },
  { key: 'mou_id', label: 'Partnership / MOU' },
  { key: 'sector', label: 'CBK sector (business)' },
];

function isConfigAdminRole(role: string | undefined, isAdmin: boolean): boolean {
  if (isAdmin) return true;
  const r = (role ?? '').toLowerCase();
  return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
}

// ── Small reusable editors ───────────────────────────────────────────────

function StringListEditor({
  items, onChange, placeholder, disabled,
}: {
  items: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState('');
  const add = () => {
    const v = draft.trim();
    if (!v || items.includes(v)) { setDraft(''); return; }
    onChange([...items, v]);
    setDraft('');
  };
  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {items.map((it) => (
          <span
            key={it}
            className="inline-flex items-center gap-1.5 rounded-full bg-gray-100 px-3 py-1 text-sm text-gray-800"
          >
            {it}
            {!disabled && (
              <button
                type="button"
                onClick={() => onChange(items.filter((x) => x !== it))}
                className="text-gray-400 hover:text-red-600"
                aria-label={`Remove ${it}`}
              >
                ×
              </button>
            )}
          </span>
        ))}
        {items.length === 0 && <span className="text-sm text-gray-400">None yet.</span>}
      </div>
      {!disabled && (
        <div className="mt-2 flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
            placeholder={placeholder ?? 'Add…'}
            className="flex-1 px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
          />
          <Button variant="ghost" size="sm" onClick={add}>Add</Button>
        </div>
      )}
    </div>
  );
}

const SubTabCtx = createContext<string>('');

const SUBTABS: { id: string; label: string }[] = [
  { id: 'lines',    label: 'Business Lines' },
  { id: 'segments', label: 'Segments' },
  { id: 'catalog',  label: 'Sectors & Categories' },
  { id: 'products', label: 'Products & Flows' },
  { id: 'mou',      label: 'MOU / Partners' },
  { id: 'org',      label: 'Committees & Branches' },
];

function PanelShell({
  title, hint, onSave, saving, children, group,
}: {
  title: string;
  hint?: string;
  onSave?: () => void;
  saving?: boolean;
  children: ReactNode;
  group?: string;
}) {
  const active = useContext(SubTabCtx);
  if (group && active && group !== active) return null;
  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">{title}</h2>
          {hint && <p className="text-xs text-gray-400 mt-0.5">{hint}</p>}
        </div>
        {onSave && (
          <Button variant="primary" size="sm" onClick={onSave} loading={saving}>
            Save
          </Button>
        )}
      </Card.Header>
      <Card.Body className="space-y-4">{children}</Card.Body>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────

export default function AdminConfig() {
  const navigate = useNavigate();
  const { user, isAdmin } = useRole();
  const { toast } = useToast();

  const allowed = useMemo(
    () => isConfigAdminRole(user?.role, isAdmin),
    [user?.role, isAdmin],
  );

  const [cfg, setCfg] = useState<PipelineConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [subTab, setSubTab] = useState('lines');

  // Local drafts
  const [required, setRequired] = useState<string[]>([]);
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [custSeg, setCustSeg] = useState<Record<string, string[]>>({});
  const [products, setProducts] = useState<Record<string, string[]>>({});
  const [mous, setMous] = useState<Mou[]>([]);
  // MOU register: add-a-partner form + search filter over the (long) list.
  const [newMouName, setNewMouName] = useState('');
  const [newMouType, setNewMouType] = useState('');
  const [newMouDept, setNewMouDept] = useState('');
  const [mouSearch, setMouSearch] = useState('');
  const [mouBusy, setMouBusy] = useState(false);
  const [sectors, setSectors] = useState<string[]>([]);
  const [dealCategories, setDealCategories] = useState<DealCategoryConfig[]>([]);
  const [clientTypes, setClientTypes] = useState<ClientType[]>([]);
  // Product flows: the authored map + which product is being edited + a draft.
  const [productFlows, setProductFlows] = useState<Record<string, ProductFlow>>({});
  const [flowProduct, setFlowProduct] = useState<string>('');
  const [flowDraft, setFlowDraft] = useState<ProductFlow>({ client_types: [], stages: [] });
  const [docCatalog, setDocCatalog] = useState<string[]>([]);
  const [newDocType, setNewDocType] = useState<string>('');
  const [addingDoc, setAddingDoc] = useState<boolean>(false);
  const [committeePalette, setCommitteePalette] = useState<CommitteeDef[]>([]);
  useEffect(() => {
    fetchCommitteePalette().then((d) => setCommitteePalette(d.committees)).catch(() => setCommitteePalette([]));
  }, []);
  function addJourneyGate(code: string) {
    setFlowDraft((f) => {
      const cur = f.committee_journey ?? [];
      return cur.includes(code) ? f : { ...f, committee_journey: [...cur, code] };
    });
  }
  function removeJourneyGate(idx: number) {
    setFlowDraft((f) => ({ ...f, committee_journey: (f.committee_journey ?? []).filter((_, i) => i !== idx) }));
  }
  function moveJourneyGate(idx: number, dir: -1 | 1) {
    setFlowDraft((f) => {
      const arr = [...(f.committee_journey ?? [])];
      const j = idx + dir;
      if (j < 0 || j >= arr.length) return f;
      [arr[idx], arr[j]] = [arr[j], arr[idx]];
      return { ...f, committee_journey: arr };
    });
  }
  useEffect(() => {
    fetchDocumentCatalog().then(setDocCatalog).catch(() => setDocCatalog([]));
  }, []);
  // WHO ATTACHES (ruling 2026-08-12). A required document used to be a bare
  // name, which silently meant "the deal owner produces this" - including for
  // papers only an analyst can write. These helpers read BOTH shapes, because
  // every existing product is configured as a list of strings and breaking
  // those to add a field would take the pilot down for no gain.
  type DocReq = string | { name: string; attached_by?: string; mandatory?: boolean };
  const docName = (d: DocReq) => (typeof d === 'string' ? d : d.name);
  const docBy = (d: DocReq) => (typeof d === 'string' ? 'owner' : (d.attached_by || 'owner'));
  const docMand = (d: DocReq) => (typeof d === 'string' ? false : Boolean(d.mandatory));

  const ATTACHERS = [
    { key: 'owner', label: 'Deal owner / RM' },
    { key: 'department_analyst', label: 'Department analyst' },
    { key: 'credit_analyst', label: 'Credit analyst' },
    { key: 'credit_admin', label: 'Credit admin' },
    { key: 'customer', label: 'Customer' },
  ];

  function toggleFlowDoc(doc: string) {
    setFlowDraft((f) => {
      const cur = (f.required_documents ?? []) as DocReq[];
      const has = cur.some((d) => docName(d) === doc);
      return {
        ...f,
        required_documents: has
          ? cur.filter((d) => docName(d) !== doc)
          // New documents default to the owner, which is what a bare string
          // always meant - so ticking one behaves exactly as it did before.
          : [...cur, { name: doc, attached_by: 'owner', mandatory: false }],
      } as typeof f;
    });
  }

  function setDocField(doc: string, patch: { attached_by?: string; mandatory?: boolean }) {
    setFlowDraft((f) => ({
      ...f,
      required_documents: ((f.required_documents ?? []) as DocReq[]).map((d) =>
        docName(d) === doc
          ? { name: docName(d), attached_by: patch.attached_by ?? docBy(d),
              mandatory: patch.mandatory ?? docMand(d) }
          : d),
    } as typeof f));
  }
  const [flowBusy, setFlowBusy] = useState(false);
  // SLA config (the single source of truth for product_promise — the overall
  // per-product end-to-end SLA budget). Loaded so the flow editor can show the
  // product's promise against the running sum of its stage target_days and flag
  // over-allocation, and let the admin adjust the promise inline. Writing here
  // saves to the SAME sla_config the SLA page + violation engine use.
  const [slaConfig, setSlaConfig] = useState<SlaConfig | null>(null);
  // Draft budget for the selected product (business days), seeded from
  // product_promise[product]; '' means no promise set (falls back to step sum).
  const [flowBudget, setFlowBudget] = useState<string>('');

  const hydrate = (c: PipelineConfig) => {
    setCfg(c);
    setRequired(c.required_fields ?? []);
    setLabels({ ...(c.segment_labels ?? {}) });
    setCustSeg({ ...(c.customer_segments ?? {}) });
    setProducts({ ...(c.product_catalogue ?? {}) });
    setMous((c.individual_mous ?? []).map((m) => ({ active: true, ...m })));
    setSectors([...(c.business_sectors ?? [])]);
    setDealCategories([...(c.deal_categories ?? [])]);
    setClientTypes((c.client_types ?? []).map((t) => ({ ...t })));
    setProductFlows({ ...(c.product_flows ?? {}) });
  };

  useEffect(() => {
    if (!allowed) { setLoading(false); return; }
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) hydrate(c); })
      .catch(() => toast({ tone: 'danger', message: 'Could not load configuration.' }))
      .finally(() => { if (active) setLoading(false); });
    // SLA config carries product_promise (the overall per-product SLA budget).
    fetchSlaConfig()
      .then((r) => { if (active) setSlaConfig(r.sla_config); })
      .catch(() => { /* non-fatal — flow editor just won't show a budget */ });
    return () => { active = false; };
  }, [allowed]);

  const save = async (key: string, patch: AdminConfigPatch, label: string) => {
    setSavingKey(key);
    try {
      const res = await updatePipelineConfig(patch);
      // Re-hydrate from the authoritative effective config the server returns.
      setCfg((prev) => (prev ? { ...prev, ...res.config } : prev));
      if (res.config.required_fields) setRequired(res.config.required_fields);
      if (res.config.segment_labels) setLabels({ ...res.config.segment_labels });
      if (res.config.customer_segments) setCustSeg({ ...res.config.customer_segments });
      if (res.config.product_catalogue) setProducts({ ...res.config.product_catalogue });
      if (res.config.deal_categories) setDealCategories([...res.config.deal_categories]);
      if (res.config.individual_mous) setMous(res.config.individual_mous.map((m) => ({ active: true, ...m })));
      if (res.config.business_sectors) setSectors([...res.config.business_sectors]);
      if (res.config.client_types) setClientTypes(res.config.client_types.map((t) => ({ ...t })));
      toast({ tone: 'success', message: `${label} saved.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : `Could not save ${label.toLowerCase()}.` });
    } finally {
      setSavingKey(null);
    }
  };

  // MOU register writes go to the dedicated /admin/mous endpoint (partnerships_
  // mous.json), NOT pipeline-config — so a newly added partner is immediately
  // selectable on a deal. Add takes a name (+ optional type/dept); the backend
  // mints the id and defaults the rest.
  const addMou = async () => {
    const name = newMouName.trim();
    if (!name) return;
    setMouBusy(true);
    try {
      const res = await upsertMou({
        partner_name: name,
        mou_type: newMouType.trim() || undefined,
        department: newMouDept.trim() || undefined,
      });
      setMous((p) => [...p, { id: res.mou.id, title: res.mou.title, partner_name: res.mou.partner_name, active: true }]);
      setNewMouName('');
      setNewMouType('');
      setNewMouDept('');
      toast({ tone: 'success', message: `Added ${res.mou.partner_name}.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not add the MOU partner.' });
    } finally {
      setMouBusy(false);
    }
  };

  const setMouActive = async (id: string, active: boolean) => {
    setMouBusy(true);
    try {
      await upsertMou({ id, status: active ? 'Active' : 'Inactive' });
      setMous((p) => p.map((m) => (m.id === id ? { ...m, active } : m)));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not update the MOU.' });
    } finally {
      setMouBusy(false);
    }
  };

  const visibleMous = useMemo(() => {
    const q = mouSearch.trim().toLowerCase();
    if (!q) return mous;
    return mous.filter((m) =>
      (m.title ?? '').toLowerCase().includes(q) ||
      (m.partner_name ?? '').toLowerCase().includes(q) ||
      (m.id ?? '').toLowerCase().includes(q));
  }, [mous, mouSearch]);

  // ── Product flows ──
  // All catalogued products, flattened, for the picker.
  const allProducts = useMemo(
    () => Array.from(new Set(Object.values(products).flat())).sort(),
    [products],
  );
  // When a product is selected, load its authored flow into the draft (or a
  // single empty stage if it has none yet).
  const selectFlowProduct = (product: string) => {
    setFlowProduct(product);
    const existing = productFlows[product];
    setFlowDraft(existing
      ? { client_types: [...existing.client_types], stages: existing.stages.map((s) => ({ ...s })), required_documents: [...(existing.required_documents ?? [])], documents_required_at_stage: existing.documents_required_at_stage ?? '', committee_journey: [...(existing.committee_journey ?? [])] }
      : { client_types: [], stages: [{ stage: '', target_days: 3, win_probability: null }], required_documents: [], documents_required_at_stage: '', committee_journey: [] });
    // Seed the overall SLA budget from the existing product_promise (if any).
    const promised = slaConfig?.product_promise?.[product];
    setFlowBudget(typeof promised === 'number' && promised > 0 ? String(promised) : '');
  };
  // Running sum of the flow's per-stage target_days, vs the overall SLA budget.
  // Over-allocation = the stages promise more days than the product's end-to-end
  // SLA, which would mean a deal can blow the product promise before it even
  // reaches the last stage. Surfaced live as the admin distributes the days.
  const flowDaysSum = useMemo(
    () => flowDraft.stages.reduce((acc, s) => {
      const t = Number(s.target_days);
      return acc + (Number.isFinite(t) && t > 0 ? t : 0);
    }, 0),
    [flowDraft.stages],
  );
  const flowBudgetNum = useMemo(() => {
    const n = Number(flowBudget);
    return flowBudget.trim() !== '' && Number.isFinite(n) && n > 0 ? n : null;
  }, [flowBudget]);
  const flowOverBudget = flowBudgetNum !== null && flowDaysSum > flowBudgetNum;

  const saveFlow = async () => {
    if (!flowProduct) return;
    const stages = flowDraft.stages
      .map((s) => {
        const wp = s.win_probability;
        const wpNum = wp === null || wp === undefined || String(wp).trim() === ''
          ? null : Number(wp);
        return {
          stage: s.stage.trim(),
          target_days: Number(s.target_days),
          // Only send a win_probability when set to a valid 0–100 number;
          // otherwise omit (the stage simply carries no derived probability).
          ...(wpNum !== null && Number.isFinite(wpNum) && wpNum >= 0 && wpNum <= 100
            ? { win_probability: wpNum } : {}),
        };
      })
      .filter((s) => s.stage && Number.isFinite(s.target_days) && s.target_days > 0);
    if (stages.length === 0) {
      toast({ tone: 'danger', message: 'Add at least one stage with a positive target.' });
      return;
    }
    setFlowBusy(true);
    try {
      await upsertProductFlow({ product: flowProduct, stages, client_types: flowDraft.client_types, required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '', committee_journey: flowDraft.committee_journey ?? [] });
      setProductFlows((p) => ({ ...p, [flowProduct]: { client_types: flowDraft.client_types, stages, required_documents: flowDraft.required_documents ?? [], documents_required_at_stage: flowDraft.documents_required_at_stage ?? '', committee_journey: flowDraft.committee_journey ?? [] } }));

      // Persist the overall SLA budget to product_promise (the SAME sla_config
      // the SLA page + violation engine use), so the two stay reconciled. A
      // blank/zero budget removes the promise (product falls back to step-sum).
      if (slaConfig) {
        const budgetNum = flowBudget.trim() === '' ? 0 : Number(flowBudget);
        const promise = { ...(slaConfig.product_promise ?? {}) };
        const had = flowProduct in promise;
        let changed = false;
        if (Number.isFinite(budgetNum) && budgetNum > 0) {
          if (promise[flowProduct] !== budgetNum) { promise[flowProduct] = budgetNum; changed = true; }
        } else if (had) {
          delete promise[flowProduct]; changed = true;
        }
        if (changed) {
          const nextSla = { ...slaConfig, product_promise: promise };
          await saveSlaConfig(nextSla);
          setSlaConfig(nextSla);
        }
      }

      toast({ tone: 'success', message: `${flowProduct} flow saved.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save the flow.' });
    } finally {
      setFlowBusy(false);
    }
  };
  const resetFlowToClass = async () => {
    if (!flowProduct) return;
    setFlowBusy(true);
    try {
      await upsertProductFlow({ product: flowProduct, delete: true });
      setProductFlows((p) => { const n = { ...p }; delete n[flowProduct]; return n; });
      setFlowDraft({ client_types: [], stages: [{ stage: '', target_days: 3, win_probability: null }] });
      toast({ tone: 'success', message: `${flowProduct} reverted to its class flow.` });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not reset the flow.' });
    } finally {
      setFlowBusy(false);
    }
  };

  if (!allowed) {
    return (
      <div className="min-h-screen bg-gray-50">
        <PageHeader
          title="Configuration"
          breadcrumbs={[{ label: 'Reference & Admin' }, { label: 'Configuration' }]}
        />
        <main className="max-w-3xl mx-auto px-6 py-10">
          <Card stripe="accent">
            <Card.Body>
              <h2 className="text-base font-semibold text-gray-900">Restricted</h2>
              <p className="mt-1 text-sm text-gray-600">
                Reference configuration can only be viewed and edited by the CEO, MD,
                or a Director. If you believe you should have access, contact your administrator.
              </p>
              <div className="mt-4">
                <Button variant="ghost" size="sm" onClick={() => navigate('/')}>← Back to dashboard</Button>
              </div>
            </Card.Body>
          </Card>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <AdminTabs subtitle="Reference data that drives the pipeline and credit factory. Changes apply on the next refresh." />

      <main className="max-w-6xl mx-auto px-6 py-6">
        {loading ? (
          <div className="py-16 text-center text-sm text-gray-500">Loading configuration…</div>
        ) : !cfg ? (
          <div className="py-16 text-center text-sm text-gray-500">Configuration unavailable.</div>
        ) : (
          <>
            <div className="mb-5 flex gap-1 overflow-x-auto border-b border-gray-200">
              {SUBTABS.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => setSubTab(s.id)}
                  className={`whitespace-nowrap border-b-2 px-3 py-2 text-sm transition-colors ${
                    subTab === s.id
                      ? 'border-[#0082BB] font-medium text-[#0082BB]'
                      : 'border-transparent text-gray-500 hover:text-gray-800'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
            <SubTabCtx.Provider value={subTab}>
          <div className="grid lg:grid-cols-2 gap-5 items-start">
            {/* Client business lines */}
            <PanelShell
              group="lines"
              title="Client business lines"
              hint="Consumer / Commercial / CIB. 'Field' picks the third selector: MOU (consumer) or CBK sector (business)."
              onSave={() =>
                save('clientTypes',
                  { client_types: clientTypes.filter((t) => t.key.trim() && t.label.trim()) },
                  'Client business lines')
              }
              saving={savingKey === 'clientTypes'}
            >
              <div className="space-y-2">
                {clientTypes.map((t, i) => (
                  <div key={`${t.key}-${i}`} className="grid grid-cols-[1.2fr_1.6fr_1fr_auto] items-center gap-2">
                    <Input
                      value={t.key}
                      placeholder="Key (stored)"
                      onChange={(e) => setClientTypes((p) => p.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))}
                    />
                    <Input
                      value={t.label}
                      placeholder="Display label"
                      onChange={(e) => setClientTypes((p) => p.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                    />
                    <select
                      value={t.field}
                      onChange={(e) => setClientTypes((p) => p.map((x, j) => (j === i ? { ...x, field: e.target.value as 'mou' | 'sector' } : x)))}
                      className="h-10 px-2 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                    >
                      <option value="mou">MOU</option>
                      <option value="sector">Sector</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => setClientTypes((p) => p.filter((_, j) => j !== i))}
                      className="text-gray-400 hover:text-red-600 px-1"
                      aria-label="Remove client type"
                    >
                      ×
                    </button>
                  </div>
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setClientTypes((p) => [...p, { key: '', label: '', field: 'sector' }])}
                >
                  + Add business line
                </Button>
              </div>
            </PanelShell>

            {/* Required fields */}
            <PanelShell
              group="lines"
              title="Required fields"
              hint="Which inputs a new deal must have before it can be created."
              onSave={() => save('required', { required_fields: required }, 'Required fields')}
              saving={savingKey === 'required'}
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {REQUIRABLE_FIELDS.map((f) => {
                  const on = required.includes(f.key);
                  return (
                    <label key={f.key} className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={() =>
                          setRequired((prev) =>
                            on ? prev.filter((k) => k !== f.key) : [...prev, f.key],
                          )
                        }
                        className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary/30"
                      />
                      {f.label}
                    </label>
                  );
                })}
              </div>
            </PanelShell>

            {/* Sectors */}
            <PanelShell
              group="catalog"
              title="CBK economic sectors"
              hint="Sector classification offered for business clients."
              onSave={() => save('sectors', { business_sectors: sectors }, 'Sectors')}
              saving={savingKey === 'sectors'}
            >
              <StringListEditor items={sectors} onChange={setSectors} placeholder="Add a sector…" />
            </PanelShell>

            {/* Pipeline categories (A2b) — balance-sheet class the bank tracks */}
            <PanelShell
              group="catalog"
              title="Pipeline categories"
              hint="Balance-sheet classes shown on the create-deal form (Loan/Asset, Deposit/Liability, Insurance). Add a new pipeline class here. Dormant categories are kept but hidden."
              onSave={() => save('deal_categories', { deal_categories: dealCategories }, 'Pipeline categories')}
              saving={savingKey === 'deal_categories'}
            >
              <CategoryEditor categories={dealCategories} onChange={setDealCategories} />
            </PanelShell>

            {/* Segment display names */}
            <PanelShell
              group="segments"
              title="Segment display names"
              hint="Map internal segment buckets to the bank's own names (e.g. Affluent → Premier)."
              onSave={() => save('labels', { segment_labels: labels }, 'Segment names')}
              saving={savingKey === 'labels'}
            >
              {Object.keys(labels).length === 0 ? (
                <p className="text-sm text-gray-400">No segment labels configured.</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(labels).map(([base, display]) => (
                    <div key={base} className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
                      <span className="text-sm text-gray-500 truncate">{base}</span>
                      <span className="text-gray-300">→</span>
                      <Input
                        value={display}
                        onChange={(e) => setLabels((p) => ({ ...p, [base]: e.target.value }))}
                      />
                    </div>
                  ))}
                </div>
              )}
            </PanelShell>

            {/* Customer segments per client business line */}
            <PanelShell
              group="segments"
              title="Customer segment options"
              hint="The segment choices offered on the deal form, per business line."
              onSave={() => {
                // Save ONLY the segment lists for the configured business lines —
                // this drops any orphaned keys (e.g. legacy Individual/Business).
                const cleaned: Record<string, string[]> = {};
                clientTypes.forEach((t) => { cleaned[t.key] = custSeg[t.key] ?? []; });
                save('custseg', { customer_segments: cleaned }, 'Customer segments');
              }}
              saving={savingKey === 'custseg'}
            >
              {clientTypes.length === 0 ? (
                <p className="text-sm text-gray-400">Define client business lines first.</p>
              ) : (
                clientTypes.map((t) => (
                  <div key={t.key}>
                    <div className="mb-1.5 text-sm font-medium text-gray-700">{t.label}</div>
                    <StringListEditor
                      items={custSeg[t.key] ?? []}
                      onChange={(next) => setCustSeg((p) => ({ ...p, [t.key]: next }))}
                      placeholder={`Add ${t.label} segment…`}
                    />
                  </div>
                ))
              )}
            </PanelShell>

            {/* Product catalogue */}
            <PanelShell
              group="products"
              title="Product catalogue"
              hint="Products offered, grouped by class. Class drives the pipeline buckets."
              onSave={() => save('products', { product_catalogue: products }, 'Product catalogue')}
              saving={savingKey === 'products'}
            >
              {Object.keys(products).length === 0 ? (
                <p className="text-sm text-gray-400">No products configured.</p>
              ) : (
                Object.entries(products).map(([cls, list]) => (
                  <div key={cls}>
                    <div className="mb-1.5 text-sm font-medium text-gray-700">{cls}</div>
                    <StringListEditor
                      items={list}
                      onChange={(next) => setProducts((p) => ({ ...p, [cls]: next }))}
                      placeholder={`Add ${cls} product…`}
                    />
                  </div>
                ))
              )}
            </PanelShell>

            {/* MOU register — writes go to the dedicated endpoint, so additions
                are immediately selectable on consumer deals. */}
            <PanelShell
              group="mou"
              title="Partnership / MOU register"
              hint="Partners offered on consumer deals. Add a partner here and it's selectable immediately."
            >
              <div className="space-y-3">
                {/* Add a partner */}
                <div className="space-y-2">
                  <Input
                    value={newMouName}
                    placeholder="Partner name"
                    onChange={(e) => setNewMouName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') addMou(); }}
                  />
                  <div className="flex flex-wrap items-center gap-2">
                    <Input
                      containerClassName="flex-1 min-w-[7rem]"
                      value={newMouType}
                      placeholder="Type (optional)"
                      onChange={(e) => setNewMouType(e.target.value)}
                    />
                    <Input
                      containerClassName="flex-1 min-w-[7rem]"
                      value={newMouDept}
                      placeholder="Department (optional)"
                      onChange={(e) => setNewMouDept(e.target.value)}
                    />
                    <Button size="sm" onClick={addMou} disabled={mouBusy || !newMouName.trim()}>
                      Add partner
                    </Button>
                  </div>
                </div>

                {/* Search the register */}
                <Input
                  value={mouSearch}
                  placeholder={`Search ${mous.length} partners…`}
                  onChange={(e) => setMouSearch(e.target.value)}
                />

                {/* List (read-only id/title; toggle Active to deactivate) */}
                <div className="max-h-72 overflow-y-auto rounded-md border border-gray-200 divide-y divide-gray-100">
                  {visibleMous.length === 0 ? (
                    <p className="px-3 py-4 text-sm text-gray-500">No partners match “{mouSearch}”.</p>
                  ) : (
                    visibleMous.map((m) => (
                      <div key={m.id} className="flex items-center gap-3 px-3 py-2 text-sm">
                        <span className="font-mono text-xs text-gray-400 w-20 shrink-0">{m.id}</span>
                        <span className="flex-1 text-gray-900">{m.title}</span>
                        <label className="flex items-center gap-1 text-xs text-gray-600 shrink-0">
                          <input
                            type="checkbox"
                            checked={m.active !== false}
                            disabled={mouBusy}
                            onChange={(e) => setMouActive(m.id, e.target.checked)}
                            className="h-4 w-4 rounded border-gray-300 text-brand-primary"
                          />
                          Active
                        </label>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </PanelShell>

            {/* Product flows — per-product stage sequence + per-stage SLA */}
            <PanelShell
              group="products"
              title="Product flows"
              hint="Each product can have its own stage sequence and per-stage target days. Pick a product to customise its flow; unset products follow their class flow."
            >
              <div className="space-y-3">
                <select
                  value={flowProduct}
                  onChange={(e) => selectFlowProduct(e.target.value)}
                  className="w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                >
                  <option value="">Select a product to edit its flow…</option>
                  {allProducts.some((p) => productFlows[p]) && (
                    <optgroup label="Products with a custom flow">
                      {allProducts.filter((p) => productFlows[p]).map((p) => (
                        <option key={p} value={p}>{p}</option>
                      ))}
                    </optgroup>
                  )}
                  <optgroup label="Using their class default">
                    {allProducts.filter((p) => !productFlows[p]).map((p) => (
                      <option key={p} value={p}>{p}</option>
                    ))}
                  </optgroup>
                </select>

                {flowProduct && (
                  <>
                    {/* Client types that offer this product */}
                    <div>
                      <p className="text-xs font-medium text-gray-600 mb-1">Offered to</p>
                      <div className="flex flex-wrap gap-2">
                        {clientTypes.map((ct) => {
                          const on = flowDraft.client_types.includes(ct.key);
                          return (
                            <button
                              key={ct.key}
                              type="button"
                              onClick={() => setFlowDraft((d) => ({
                                ...d,
                                client_types: on
                                  ? d.client_types.filter((k) => k !== ct.key)
                                  : [...d.client_types, ct.key],
                              }))}
                              className={`px-2.5 py-1 rounded-full text-xs border ${on
                                ? 'bg-brand-primary/10 border-brand-primary text-brand-primary'
                                : 'bg-white border-gray-300 text-gray-600'}`}
                            >
                              {ct.label}
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-xs text-gray-400 mt-1">
                        {flowDraft.client_types.length === 0
                          ? 'No selection = offered to all client types.'
                          : 'Offered only to the selected client types.'}
                      </p>
                    </div>

                    {/* Overall product SLA budget (product_promise) — the
                        single source of truth used by the SLA module + violation
                        engine. Distribute the per-stage days under this ceiling. */}
                    <div className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="text-xs font-medium text-gray-700">Overall SLA (create → closed)</p>
                          <p className="text-[11px] text-gray-400">
                            Business days. This is the product promise the violation engine references.
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <Input
                            value={flowBudget}
                            type="number"
                            placeholder="—"
                            min={0}
                            className="w-20"
                            onChange={(e) => setFlowBudget(e.target.value)}
                          />
                          <span className="text-xs text-gray-500">bd</span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-gray-600">
                          Distributed across stages: <span className="font-semibold text-gray-900">{flowDaysSum} bd</span>
                        </span>
                        {flowBudgetNum !== null && (
                          flowOverBudget ? (
                            <Badge tone="danger" size="sm">
                              Over by {flowDaysSum - flowBudgetNum} bd
                            </Badge>
                          ) : (
                            <Badge tone="success" size="sm">
                              {flowBudgetNum - flowDaysSum} bd to spare
                            </Badge>
                          )
                        )}
                      </div>
                      {flowOverBudget && (
                        <p className="text-[11px] text-red-600">
                          The stage days exceed the overall SLA — a deal would breach the product
                          promise before reaching the final stage. Reduce stage targets or raise the SLA.
                        </p>
                      )}
                    </div>

                    {/* Stage sequence with per-stage target_days + win probability */}
                    <div className="space-y-2">
                      <div className="grid grid-cols-[1fr_5rem_5rem_auto] items-center gap-2">
                        <p className="text-xs font-medium text-gray-600">Stage</p>
                        <p className="text-xs font-medium text-gray-600 text-center">Days</p>
                        <p className="text-xs font-medium text-gray-600 text-center">Win&nbsp;%</p>
                        <span />
                      </div>
                      {flowDraft.stages.map((s, i) => (
                        <div key={i} className="grid grid-cols-[1fr_5rem_5rem_auto] items-center gap-2">
                          <Input
                            value={s.stage}
                            placeholder={`Stage ${i + 1}`}
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i ? { ...x, stage: e.target.value } : x)),
                            }))}
                          />
                          <Input
                            value={String(s.target_days)}
                            type="number" step="any"
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i ? { ...x, target_days: Number(e.target.value) } : x)),
                            }))}
                          />
                          <Input
                            value={s.win_probability === null || s.win_probability === undefined
                              ? '' : String(s.win_probability)}
                            type="number"
                            placeholder="—"
                            min={0}
                            max={100}
                            onChange={(e) => setFlowDraft((d) => ({
                              ...d,
                              stages: d.stages.map((x, j) => (j === i
                                ? { ...x, win_probability: e.target.value === '' ? null : Number(e.target.value) }
                                : x)),
                            }))}
                          />
                          <div className="flex items-center gap-0.5">
                            <button
                              type="button"
                              onClick={() => setFlowDraft((d) => ({
                                ...d,
                                stages: [
                                  ...d.stages.slice(0, i),
                                  { stage: '', target_days: 3, win_probability: null },
                                  ...d.stages.slice(i),
                                ],
                              }))}
                              className="px-1 text-sm text-gray-400 hover:text-[#0082BB]"
                              aria-label="Insert a stage above this one"
                              title="Insert a stage above this one"
                            >
                              +↑
                            </button>
                            <button
                              type="button"
                              onClick={() => setFlowDraft((d) => ({
                                ...d, stages: d.stages.filter((_, j) => j !== i),
                              }))}
                              className="text-gray-400 hover:text-red-600 px-1"
                              aria-label="Remove stage"
                            >
                              ×
                            </button>
                          </div>
                        </div>
                      ))}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setFlowDraft((d) => ({
                          ...d, stages: [...d.stages, { stage: '', target_days: 3, win_probability: null }],
                        }))}
                      >
                        + Add stage
                      </Button>
                      <p className="text-[11px] text-gray-400">
                        Win&nbsp;% is the likelihood of closing a deal sitting at that stage. A deal
                        inherits its current stage&apos;s value automatically — leave blank for none.
                        Use <span className="font-medium">+↑</span> on a row to insert a stage above it; <span className="font-medium">+ Add stage</span> appends to the end.
                      </p>
                    </div>

                    <div className="space-y-3 pt-1">
                      <div className="rounded border p-3">
                <p className="mb-1 text-sm font-medium">Required documents (this product)</p>
                <p className="mb-2 text-xs text-gray-500">Tick documents this product requires. Choose the stage they must be attached at.</p>
                <div className="mb-2 grid max-h-40 grid-cols-2 gap-x-4 gap-y-1 overflow-auto rounded border p-2">
                  {docCatalog.map((doc) => (
                    <label key={doc} className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={((flowDraft.required_documents ?? []) as DocReq[]).some((d) => docName(d) === doc)} onChange={() => toggleFlowDoc(doc)} />
                      {doc}
                    </label>
                  ))}
                </div>
                {/* WHO ATTACHES EACH ONE, and whether it blocks. Two settings per
                    document, shown only for the ones actually ticked - a
                    dropdown beside all sixty catalogue entries would be noise. */}
                {((flowDraft.required_documents ?? []) as DocReq[]).length > 0 && (
                  <div className="mb-3 overflow-hidden rounded border">
                    <div className="grid grid-cols-[1fr_180px_110px] gap-2 border-b bg-gray-50 px-2 py-1 text-[11px] font-medium text-gray-600">
                      <span>Document</span>
                      <span>Attached by</span>
                      <span>Blocks submission</span>
                    </div>
                    {((flowDraft.required_documents ?? []) as DocReq[]).map((d) => (
                      <div key={docName(d)}
                           className="grid grid-cols-[1fr_180px_110px] items-center gap-2 border-b px-2 py-1.5 text-sm last:border-b-0">
                        <span className="truncate text-gray-800">{docName(d)}</span>
                        <select
                          className="h-8 rounded border border-gray-300 px-1 text-xs"
                          value={docBy(d)}
                          onChange={(e) => setDocField(docName(d), { attached_by: e.target.value })}>
                          {ATTACHERS.map((a) => (
                            <option key={a.key} value={a.key}>{a.label}</option>
                          ))}
                        </select>
                        <label className="flex items-center gap-1.5 text-xs text-gray-600">
                          <input type="checkbox" checked={docMand(d)}
                                 onChange={(e) => setDocField(docName(d), { mandatory: e.target.checked })} />
                          mandatory
                        </label>
                      </div>
                    ))}
                    <p className="px-2 py-1.5 text-[11px] text-gray-500">
                      Only <strong>mandatory</strong> documents block submission. Everything
                      else can be submitted pending and attached as the analysis
                      progresses — and a document assigned to an analyst never blocks
                      the deal owner, who has no way of producing it.
                    </p>
                  </div>
                )}

                {/* Admin: introduce a NEW document type into the global master list.
                    Once added it appears above as a tickable checkbox for any product. */}
                <div className="mb-2 flex items-center gap-2">
                  <input
                    type="text"
                    className="flex-1 rounded border px-2 py-1.5 text-sm"
                    placeholder="Add a new document type (e.g. Board Resolution)…"
                    value={newDocType}
                    onChange={(e) => setNewDocType(e.target.value)}
                  />
                  <button
                    type="button"
                    className="rounded border px-3 py-1.5 text-sm text-brand-primary hover:bg-gray-50 disabled:opacity-50"
                    disabled={!newDocType.trim() || addingDoc}
                    onClick={async () => {
                      const nm = newDocType.trim();
                      if (!nm) return;
                      setAddingDoc(true);
                      try {
                        const docs = await addDocumentType(nm);
                        setDocCatalog(docs);
                        setNewDocType('');
                      } catch { /* surfaced via disabled state; keep input */ }
                      finally { setAddingDoc(false); }
                    }}
                  >
                    {addingDoc ? 'Adding…' : 'Add type'}
                  </button>
                </div>
                <label className="mb-1 block text-xs font-medium text-gray-600">Documents required at stage</label>
                <select
                  className="w-full rounded border px-2 py-1.5 text-sm"
                  value={flowDraft.documents_required_at_stage ?? ''}
                  onChange={(e) => setFlowDraft((f) => ({ ...f, documents_required_at_stage: e.target.value }))}
                >
                  <option value="">— none —</option>
                  {flowDraft.stages.filter((s) => s.stage.trim()).map((s) => (
                    <option key={s.stage} value={s.stage}>{s.stage}</option>
                  ))}
                </select>
              </div>
              <div className="rounded border p-3">
                <p className="mb-1 text-sm font-medium">Credit committee journey (this product)</p>
                <p className="mb-2 text-xs text-gray-500">Ordered committee gates this product opens before Credit Analysis. Empty = CR only. Amount-triggered committees are added automatically.</p>
                {(flowDraft.committee_journey ?? []).length === 0 && (
                  <p className="mb-2 text-xs text-gray-400">No committees — CR-only path.</p>
                )}
                <ol className="mb-2 space-y-1">
                  {(flowDraft.committee_journey ?? []).map((code, i) => {
                    const def = committeePalette.find((c) => c.code === code);
                    return (
                      <li key={code} className="flex items-center justify-between rounded border px-2 py-1 text-sm">
                        <span>{i + 1}. {def ? `${def.code} — ${def.name}` : code}</span>
                        <span className="flex gap-1">
                          <button type="button" className="text-xs text-gray-500 hover:text-gray-800" onClick={() => moveJourneyGate(i, -1)}>up</button>
                          <button type="button" className="text-xs text-gray-500 hover:text-gray-800" onClick={() => moveJourneyGate(i, 1)}>down</button>
                          <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => removeJourneyGate(i)}>remove</button>
                        </span>
                      </li>
                    );
                  })}
                </ol>
                <div className="flex items-center gap-2">
                  <select id="journeyAdd" className="rounded border px-2 py-1.5 text-sm"
                    onChange={(e) => { if (e.target.value) { addJourneyGate(e.target.value); e.target.value = ''; } }}
                    defaultValue="">
                    <option value="">+ Add committee gate…</option>
                    {committeePalette
                      .filter((c) => !(flowDraft.committee_journey ?? []).includes(c.code))
                      .map((c) => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
                  </select>
                </div>
              </div>
                      <div className="flex items-center gap-2">
                        <Button size="sm" onClick={saveFlow} disabled={flowBusy}>
                          Save flow
                        </Button>
                        {productFlows[flowProduct] && (
                          <Button variant="secondary" size="sm" onClick={resetFlowToClass} disabled={flowBusy}>
                            Reset to class flow
                          </Button>
                        )}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </PanelShell>

            {/* Committee tiers — the multi-tier credit committee ladder. */}
            {subTab === 'org' && (
              <>
                <CommitteeTiersPanel />
                <BranchesPanel />
              </>
            )}
          </div>
            </SubTabCtx.Provider>
          </>
        )}
      </main>
    </div>
  );
}


// ─── Committee tiers panel ─────────────────────────────────────────────
// Self-contained: loads + saves the multi-tier credit committee ladder via
// the dedicated /api/lms/committee/tiers endpoint, independent of the main
// pipeline config flow. Lets the business rename tiers, set authority limits,
// and control which tiers permit direct entry (CIB leeway).
function CommitteeTiersPanel() {
  const { toast } = useToast();
  const [tiers, setTiers] = useState<CommitteeTier[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    getCommitteeTiers()
      .then((r) => { if (live) setTiers(r.tiers || []); })
      .catch(() => toast({ tone: 'danger', message: 'Could not load committee tiers.' }))
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [toast]);

  const update = (i: number, patch: Partial<CommitteeTier>) =>
    setTiers((prev) => prev.map((t, idx) => (idx === i ? { ...t, ...patch } : t)));

  const addTier = () => {
    const nextNum = tiers.length ? Math.max(...tiers.map((t) => t.tier)) + 1 : 1;
    setTiers((prev) => [...prev, {
      tier: nextNum, key: `tier_${nextNum}`, name: '',
      authority_limit_kes: null, can_be_entry: true,
    }]);
  };
  const removeTier = (i: number) => setTiers((prev) => prev.filter((_, idx) => idx !== i));

  const save = async () => {
    setSaving(true);
    try {
      const r = await saveCommitteeTiers(tiers);
      setTiers(r.tiers || []);
      toast({ tone: 'success', message: 'Committee tiers saved.' });
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save tiers.' });
    } finally { setSaving(false); }
  };

  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">Credit committee tiers</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            The ordered committee ladder. A case enters at a tier and the committee submits it
            upward as needed. Limits inform routing; entry-permitted tiers can be skipped to.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={save} loading={saving} disabled={loading}>
          Save
        </Button>
      </Card.Header>
      <Card.Body className="space-y-3">
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <>
            <div className="hidden md:grid grid-cols-[60px_1fr_1.2fr_110px_auto] gap-2 text-xs text-gray-500 px-1">
              <span>Tier</span><span>Name</span><span>Authority limit (KES)</span><span>Entry?</span><span></span>
            </div>
            {tiers.map((t, i) => (
              <div key={i} className="grid grid-cols-1 md:grid-cols-[60px_1fr_1.2fr_110px_auto] gap-2 items-center">
                <Input value={String(t.tier)} onChange={(e) => update(i, { tier: Number(e.target.value) || t.tier })} disabled={saving} />
                <Input value={t.name} placeholder="Tier name" onChange={(e) => update(i, { name: e.target.value })} disabled={saving} />
                <Input
                  value={t.authority_limit_kes == null ? '' : String(t.authority_limit_kes)}
                  placeholder="No ceiling"
                  onChange={(e) => update(i, { authority_limit_kes: e.target.value === '' ? null : Number(e.target.value) })}
                  disabled={saving}
                />
                <label className="flex items-center gap-1.5 text-sm text-gray-700">
                  <input type="checkbox" checked={t.can_be_entry}
                    onChange={(e) => update(i, { can_be_entry: e.target.checked })} disabled={saving} />
                  Entry
                </label>
                <Button variant="ghost" size="sm" onClick={() => removeTier(i)} disabled={saving}>Remove</Button>
              </div>
            ))}
            <Button variant="secondary" size="sm" onClick={addTier} disabled={saving}>Add tier</Button>
          </>
        )}
      </Card.Body>
    </Card>
  );
}


// ─── Branches & regions panel (SW-1) ───────────────────────────────────
// Self-contained: loads + saves branches via /api/admin/branches. org_config
// is the single source of truth for branch→region mapping; the server rebuilds
// the in-memory region maps on save so edits are live without a restart.
function BranchesPanel() {
  const { toast } = useToast();
  const [branches, setBranches] = useState<AdminBranch[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState<Record<string, AdminBranch>>({});

  const load = async () => {
    try {
      const r = await getAdminBranches();
      setBranches(r.branches || []);
    } catch {
      toast({ tone: 'danger', message: 'Could not load branches.' });
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(); /* eslint-disable-next-line */ }, []);

  const edit = (id: string, patch: Partial<AdminBranch>) => {
    setBranches((prev) => prev.map((b) => (b.id === id ? { ...b, ...patch } : b)));
    setDirty((d) => ({ ...d, [id]: { ...(d[id] || { id }), ...patch, id } as AdminBranch }));
  };

  const save = async () => {
    const edits = Object.values(dirty);
    if (edits.length === 0) { toast({ tone: 'info', message: 'No changes to save.' }); return; }
    setSaving(true);
    try {
      await saveAdminBranches(edits);
      setDirty({});
      toast({ tone: 'success', message: `Saved ${edits.length} branch change(s).` });
      await load();
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not save branches.' });
    } finally { setSaving(false); }
  };

  return (
    <Card stripe="primary">
      <Card.Header>
        <div>
          <h2 className="text-base font-semibold text-gray-900">Branches &amp; regions</h2>
          <p className="text-xs text-gray-400 mt-0.5">
            Edit a branch's region or area. Saved changes update the live region map immediately.
          </p>
        </div>
        <Button variant="primary" size="sm" onClick={save} loading={saving} disabled={loading}>Save</Button>
      </Card.Header>
      <Card.Body className="space-y-3">
        {loading ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <>
            <div className="hidden md:grid grid-cols-[1fr_1fr_1fr_80px] gap-2 text-xs text-gray-500 px-1">
              <span>Branch</span><span>Region (DSA)</span><span>Area (mainstream)</span><span>Active</span>
            </div>
            {branches.map((b) => (
              <div key={b.id} className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_80px] gap-2 items-center">
                <span className="text-sm font-medium text-gray-800">{b.name}</span>
                <Input value={b.region || ''} placeholder="Region"
                  onChange={(e) => edit(b.id!, { region: e.target.value })} disabled={saving} />
                <Input value={b.area_name || ''} placeholder="Area"
                  onChange={(e) => edit(b.id!, { area_name: e.target.value })} disabled={saving} />
                <label className="flex items-center gap-1.5 text-sm text-gray-700">
                  <input type="checkbox" checked={b.active !== false}
                    onChange={(e) => edit(b.id!, { active: e.target.checked })} disabled={saving} />
                </label>
              </div>
            ))}
          </>
        )}
      </Card.Body>
    </Card>
  );
}


// ── A2b: Pipeline category editor ──────────────────────────────────────
const PRODUCT_CLASSES = ['asset', 'liability', 'insurance', 'other'] as const;

function CategoryEditor({
  categories, onChange,
}: {
  categories: DealCategoryConfig[];
  onChange: (next: DealCategoryConfig[]) => void;
}) {
  const [newName, setNewName] = useState('');

  const update = (i: number, patch: Partial<DealCategoryConfig>) => {
    onChange(categories.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  };
  const remove = (i: number) => onChange(categories.filter((_, j) => j !== i));
  const add = () => {
    const name = newName.trim();
    if (!name || categories.some((c) => c.category === name)) return;
    onChange([...categories, {
      category: name, product_class: ['asset'], surface: 'pipeline',
      stages: ['Lead', 'Prospecting', 'Proposal', 'Negotiation', 'Closed Won', 'Closed Lost'],
    }]);
    setNewName('');
  };
  const toggleClass = (i: number, cls: string) => {
    const cur = categories[i].product_class ?? [];
    update(i, { product_class: cur.includes(cls) ? cur.filter((x) => x !== cls) : [...cur, cls] });
  };

  return (
    <div className="space-y-3">
      {categories.map((c, i) => {
        const dormant = (c.surface ?? 'pipeline') === 'dormant';
        return (
          <div key={c.category} className={`rounded border p-3 ${dormant ? 'bg-gray-50 opacity-70' : ''}`}>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-sm font-semibold">{c.category}</span>
              <div className="flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-gray-600">
                  <input type="checkbox" checked={!dormant}
                    onChange={(e) => update(i, { surface: e.target.checked ? 'pipeline' : 'dormant' })} />
                  Shown on create-deal
                </label>
                <button type="button" className="text-xs text-red-600 hover:underline" onClick={() => remove(i)}>remove</button>
              </div>
            </div>
            <div className="mb-2">
              <span className="mr-2 text-xs text-gray-500">Product classes:</span>
              {PRODUCT_CLASSES.map((cls) => (
                <label key={cls} className="mr-3 inline-flex items-center gap-1 text-xs">
                  <input type="checkbox" checked={(c.product_class ?? []).includes(cls)}
                    onChange={() => toggleClass(i, cls)} />
                  {cls}
                </label>
              ))}
            </div>
            <div>
              <span className="mb-1 block text-xs text-gray-500">Stages (initial flow; a product's own flow overrides):</span>
              <StringListEditor
                items={c.stages ?? []}
                onChange={(items) => update(i, { stages: items })}
                placeholder="Add a stage…"
              />
            </div>
          </div>
        );
      })}
      <div className="flex items-center gap-2 pt-2">
        <input
          className="flex-1 rounded border border-gray-300 px-3 py-1.5 text-sm"
          placeholder="New pipeline category name (e.g. Trade Finance)…"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <Button size="sm" onClick={add} disabled={!newName.trim()}>Add category</Button>
      </div>
    </div>
  );
}
'''

AUDIT_SRC = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Walk a deal from capture to disbursement. READ ONLY unless --live. Exit 1 on a block.

RULING (2026-08-12): "today the pilot has to see a case travel from a deal to
disbursement. You can also audit that journey and confirm that there are no
hidden bugs."

WHY A WALK RATHER THAN A REVIEW. Reading the code tells you what each step
intends; only walking it tells you whether step 4 accepts what step 3 produced.
Every expensive bug on this system so far has lived in that seam - the DB sync
dropping event_id, the funnel bucket the seeder never filled, the settings file
thinned by a bare except. None of them were visible in the file that contained
them.

WHAT IT CHECKS, in the order a real deal meets them:

    1  the journey is configured and reachable end to end
    2  every stage transition the flow declares is actually permitted
    3  the document gate - what it demands, and WHO can satisfy it
    4  the manager-validation gate
    5  the credit handoff (does an application get created, and linked back)
    6  the credit-admin and disbursement steps
    7  the labels a person actually reads at each step

A BLOCK is something that stops the deal. A WARNING is something that will
confuse the person driving it. Both are reported; only blocks fail the run.

    python scripts\\audit_deal_journey.py
    python scripts\\audit_deal_journey.py --product "Business Term Loan"
"""
import os
import sys

sys.path.insert(0, os.getcwd())

BLOCKS, WARNINGS = [], []


def block(what, detail=""):
    BLOCKS.append((what, detail))
    print("  BLOCK  %s" % what)
    if detail:
        print("         %s" % detail)


def warn(what, detail=""):
    WARNINGS.append((what, detail))
    print("  warn   %s" % what)
    if detail:
        print("         %s" % detail)


def ok(what, detail=""):
    print("  ok     %-44s %s" % (what, detail))


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def main():
    product = "Business Term Loan"
    if "--product" in sys.argv:
        i = sys.argv.index("--product")
        if i + 1 < len(sys.argv):
            product = sys.argv[i + 1]

    try:
        from utils.core import get_pipeline_settings
        from utils.pipeline_funnel import buckets_for
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    cfg = get_pipeline_settings() or {}

    rule("1. IS THE JOURNEY CONFIGURED END TO END?")
    flows = cfg.get("stage_flows") or {}
    flow_key = None
    prod_flows = cfg.get("product_flows") or {}
    entry = prod_flows.get(product) if isinstance(prod_flows, dict) else None
    if isinstance(entry, dict) and entry.get("stages"):
        stages = [str(s.get("stage", "")).strip() for s in entry["stages"]]
        flow_key = "product:%s" % product
    else:
        # Fall back to the class flow the deal would actually resolve to.
        for key in ("asset", "loan", "default"):
            if isinstance(flows.get(key), list) and flows[key]:
                stages = [str(x) for x in flows[key]]
                flow_key = key
                break
        else:
            stages = []
    if not stages:
        block("no stage flow resolves for %r" % product,
              "the deal would have nowhere to advance to")
        return 1
    ok("flow resolved", "%s - %d stages" % (flow_key, len(stages)))
    for n, st in enumerate(stages, 1):
        print("         %2d. %s" % (n, st))

    terminal = [s for s in stages if s.lower().startswith("closed")]
    if not terminal:
        warn("no terminal stage in the flow",
             "nothing marks the deal finished; it can be advanced for ever")

    rule("2. DOES EVERY DECLARED TRANSITION EXIST?")
    # settings["stages"] is a LEGACY generic sales list - Prospecting, Needs
    # Analysis, Proposal - left over from before the banking journey existed.
    # The advance endpoint validates against _stage_flow_for(), NOT against it.
    #
    # The first version of this audit compared the two and reported eight
    # stages as rejected, which would have been catastrophic and is not true.
    # Checked instead: does the advance path consult that list at all?
    api_src = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    ai = api_src.find('@app.post("/api/pipeline/deals/{deal_id}/advance")')
    aseg = api_src[ai:ai + 4000] if ai > 0 else ""
    if aseg and '"stages"' in aseg:
        block("the advance endpoint validates against settings['stages']",
              "which still holds the legacy sales list, so the banking stages "
              "would be refused")
    elif aseg:
        ok("advance validates against the product flow", "not the legacy list")
    else:
        warn("advance endpoint not found", "could not verify what it validates")

    legacy = [str(s.get("stage", s) if isinstance(s, dict) else s)
              for s in (cfg.get("stages") or [])]
    if legacy and not set(stages) & set(legacy):
        warn("settings['stages'] shares nothing with the live journey",
             "it is dead config (%d entries) - harmless today, but the next "
             "person to read it will believe it is the pipeline" % len(legacy))

    rule("3. THE DOCUMENT GATE")
    docs = (entry or {}).get("required_documents") or []
    at_stage = str((entry or {}).get("documents_required_at_stage", "") or "")
    if not docs:
        warn("no documents configured for %r" % product,
             "the gate passes trivially - fine today, but nothing is being asked for")
    else:
        ok("documents configured", "%d required" % len(docs))
        if at_stage and at_stage not in stages:
            block("documents_required_at_stage %r is not in the flow" % at_stage,
                  "the gate can never be reached, so it never releases")
        elif at_stage:
            ok("required at", at_stage)

        # WHO ATTACHES. A flat list of names says nothing about who is
        # responsible, so every document lands on the deal owner - including
        # the ones only an analyst can produce.
        shaped = [d for d in docs if isinstance(d, dict)]
        if not shaped:
            warn("no document says WHO attaches it",
                 "every one falls to the deal owner, including analyst-produced "
                 "papers the owner cannot obtain")

    rule("4. GATES BETWEEN THE OWNER AND CREDIT")
    src = open(os.path.join("utils", "api.py"), encoding="utf-8").read()
    i = src.find('@app.post("/api/pipeline/deals/{deal_id}/submit-to-credit")')
    # To the NEXT endpoint, not a fixed byte count. A window sized in bytes
    # silently truncates the moment the endpoint grows, and then reports the
    # things past the cut as missing - which is what happened the first time
    # this ran after the soft gate was added.
    j = src.find("\n@app.", i + 10) if i > 0 else -1
    seg = src[i:j if j > 0 else i + 12000] if i > 0 else ""
    if not seg:
        block("submit-to-credit endpoint not found")
    else:
        if "manager_validated" in seg:
            ok("manager validation is required", "deliberate control point")
        else:
            warn("no manager-validation gate", "an unvalidated deal can reach credit")
        if 'detail="Cannot submit to credit — missing documents' in seg:
            # This is the hard condition the pilot flagged.
            block("the document gate is ALL-OR-NOTHING",
                  "one outstanding paper blocks submission entirely, even when it "
                  "is not what the analysis is waiting for")
        else:
            ok("document gate allows partial submission", "")

    rule("5. THE CREDIT HANDOFF")
    if "create_from_pipeline_deal" in seg:
        ok("an application is created on submit", "")
    else:
        block("no application is created", "the deal reaches credit with nothing to work on")
    if "lms_application_id" in src or "application_id" in seg:
        ok("the application id is linked back to the deal", "")
    else:
        warn("no link back from the deal to its application",
             "somebody on the deal cannot find the credit case")

    rule("6. CREDIT ADMIN AND DISBURSEMENT")
    for label, needle in (("offer letter step", "Offer Letter"),
                          ("security perfection step", "Legal - Security Perfection"),
                          ("disbursement step", "Disbursement")):
        if needle in stages:
            ok(label, needle)
        else:
            warn("%s missing from the flow" % label,
                 "the deal cannot reach it by advancing")

    rule("7. WHAT THE PERSON READS")
    try:
        pdd = open(os.path.join("frontend", "web", "src", "pages",
                                "PipelineDealDetail.tsx"), encoding="utf-8").read()
    except OSError:
        pdd = ""
    # Look at the JSX the button RENDERS, not anywhere in the file - the phrase
    # also appears in comments explaining why it was wrong, and matching those
    # made the audit report a fix as a fault.
    import re as _re
    btn = _re.search(r"<Button[^>]*>\s*\{?([^<}]{0,60})", pdd)
    label = (btn.group(1).strip() if btn else "")
    if "Submit to Credit Analysis" in pdd and "submit_label" not in pdd:
        # The advance is one stage, config-driven and correct. The LABEL is not.
        nxt = ""
        if "Documentation" in stages:
            k = stages.index("Documentation")
            if k + 1 < len(stages):
                nxt = stages[k + 1]
        block("the button says 'Submit to Credit Analysis'",
              "but the deal advances ONE stage, which from Documentation is %r. "
              "The label names a step three transitions away." % (nxt or "the next stage"))
    elif "submit_label" in pdd:
        ok("the submit button names the real next stage",
           "from the flow, per product")
    else:
        warn("could not determine the submit label", label[:40])

    rule("VERDICT")
    if not BLOCKS:
        print("A deal can travel from capture to disbursement.")
        if WARNINGS:
            print("%d warning(s) - none stop the deal, all will confuse somebody."
                  % len(WARNINGS))
        return 0
    print("%d BLOCK(S) between a deal and disbursement:\n" % len(BLOCKS))
    for what, detail in BLOCKS:
        print("   * %s" % what)
        if detail:
            print("     %s" % detail)
    if WARNINGS:
        print("\n%d warning(s) as well." % len(WARNINGS))
    return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, ADMIN, DETAIL, APITS):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    det = open(DETAIL, encoding="utf-8").read()

    if "DOC_ATTACHERS" in api:
        print("ABORT: DOC1 looks applied.")
        return 1
    for name, blob, needle in (("api", api, MODEL_ANCHOR), ("api", api, EP_ANCHOR),
                               ("api", api, VALID_OLD), ("api", api, GATE_OLD),
                               ("api.ts", ts, TS_ANCHOR)):
        if blob.count(needle) != 1:
            print("ABORT: an anchor in %s matched %d times." % (name, blob.count(needle)))
            return 1

    api = api.replace(MODEL_ANCHOR, MODEL + MODEL_ANCHOR, 1)
    api = api.replace(VALID_OLD, VALID_NEW, 1)
    api = api.replace(GATE_OLD, SOFT_GATE, 1)
    api = api.replace(EP_ANCHOR, ENDPOINT + EP_ANCHOR, 1)
    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  document model, soft gate, next-step endpoint, client")

    # ANCHORED, so this applies on top of Alex's own additions to the file.
    for old, new in DETAIL_EDITS:
        if det.count(old) != 1:
            print("ABORT: a deal-detail anchor matched %d times:" % det.count(old))
            print("       %s" % old.strip().split("\n")[0][:70])
            print("       This file carries pilot-side changes; a whole-file")
            print("       replacement would erase them, so it must be anchored.")
            return 1
        det = det.replace(old, new, 1)
    print("  ok  deal detail - %d anchored edits" % len(DETAIL_EDITS))

    # The gate must be soft, but not toothless.
    if "mandatory" not in SOFT_GATE:
        print("ABORT: nothing can block any more - the gate is toothless.")
        return 1
    if "documents_outstanding" not in SOFT_GATE:
        print("ABORT: outstanding documents are not recorded, so submitting")
        print("       pending would mean forgetting rather than deferring.")
        return 1
    if 'attached_by="owner"' not in SOFT_GATE:
        print("ABORT: the gate still weighs documents the owner cannot produce.")
        return 1
    if "submit_label" not in ENDPOINT:
        print("ABORT: the endpoint does not return a label for the button.")
        return 1
    if "setDocField" not in ADMIN_SRC or "Attached by" not in ADMIN_SRC:
        print("ABORT: the admin cannot set who attaches a document.")
        return 1
    print("  ok  post-checks: soft but not toothless, recorded, admin can set it")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (DETAIL, det),
                          (ADMIN, ADMIN_SRC)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)
    if not os.path.exists(AUDIT):
        open(AUDIT, "w", encoding="utf-8", newline="").write(AUDIT_SRC)
        print("CREATED %s" % AUDIT)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Then walk the journey and confirm it is clear:")
    print("  python scripts\\audit_deal_journey.py")
    print("")
    print("Admin > product flow > Required documents now has a row per document")
    print("with WHO ATTACHES and whether it BLOCKS. Existing products keep")
    print("working unchanged - a bare name still means the owner.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
