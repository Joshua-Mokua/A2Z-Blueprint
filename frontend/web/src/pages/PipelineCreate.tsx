// v10.512 Phase 4 Batch β3 — PipelineCreate page.
//
// Form at /pipeline/new for creating a new pipeline deal. Covers the
// happy path AND the α5 portfolio-conflict resolution (Refer / Seek
// permission / Override-with-note).
//
// Architecture note — Streamlit/backend semantic inversion:
//   Streamlit's `_bsc_credit` calculation in pages/3_pipeline.py inverts
//   the bsc_credit_to value relative to what the backend rules in
//   utils/api_pipeline_mutations.py::is_override_semantics expect:
//
//   Streamlit "Seek permission"  → bsc_credit_to = creator      (me)
//   Streamlit "Pursue (override)" → bsc_credit_to = portfolio_owner
//
//   Backend rules:
//   bsc_credit_to == portfolio_owner_name → seek-permission (no note)
//   bsc_credit_to == anything else          → override (note required)
//
//   So Streamlit's "Seek permission" payload triggers the backend's
//   OVERRIDE rule and fails validation (no note collected). This is
//   the α5 doctrine note's "latent UX bug surfaced in α5 inspection."
//
//   This page implements the BACKEND's semantics — internally
//   consistent, server-validated. A future batch should fix Streamlit
//   to match (not β3 scope). Documenting the divergence in REVIVAL_LEDGER
//   is part of β3's deliverable.
//
// Deliberately NOT in β3 (deferred to later batches):
//   - CBS auto-lookup (needs new GET /api/cbs/customer/{cif} endpoint)
//   - Product dropdown driven by GET /api/pipeline/products
//   - Duplicate detection across deals (client-side scan or server endpoint)
//   - Backup staff selector
//   - Save-as-draft path
//   - Sector / decision-level / ID type / phone fields
//   - Competitors multiselect
//   - Linked deals for accounts pipeline
//   - Manager "assign to" override

import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useToast } from '@/components/Toast';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { useFxRates } from '@/hooks/useFxRates';
import { Card } from '@/components/Card';
import { StaffPicker } from '@/components/StaffPicker';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/Button';
import { Input } from '@/components/Input';
import { CustomerSearchInput } from '@/components/CustomerSearchInput';
import { fetchCbsCustomer, fetchPipelineConfig, fetchCustomerPortfolioOwner, ApiValidationError, type CustomerPortfolioOwner, type StaffMember } from '@/lib/api';
import {
  PIPELINE_CATEGORIES, INITIAL_STAGES_BY_CATEGORY,
  COMMON_PRODUCTS_BY_CATEGORY, SOURCE_OPTIONS,
  MIN_OVERRIDE_NOTE_LEN,
  type PipelineCategory, type CreateDealRequest, type ReferDealRequest,
  type PipelineConfig,
} from '@/types/pipeline';
import { segmentToCustomerType, type CbsCustomer } from '@/types/cbs';


// ── Conflict resolution path discriminator ──────────────────────────────

type ConflictPath = 'refer' | 'seek_permission' | 'override';


// ── Page component ──────────────────────────────────────────────────────

// Map a product to its class (asset/liability/insurance/other) using the
// admin product_catalogue, mirroring the backend _classify_product: exact
// match first, then containment. Drives which stage_flow the create form's
// Initial-stage dropdown follows. Returns null when no catalogue is loaded so
// the caller can fall back to the legacy category map.
type ProductClass = 'asset' | 'liability' | 'insurance' | 'other';
const PRODUCT_CLASS_MAP: Record<string, ProductClass> = {
  Assets: 'asset',
  Liabilities: 'liability',
  Insurance: 'insurance',
  Transactional: 'other',
  Investments: 'other',
};
function classifyProduct(
  productType: string,
  catalogue?: Record<string, string[]>,
): ProductClass | null {
  if (!catalogue) return null;
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  const n = norm(productType);
  if (!n) return null;
  for (const [cls, prods] of Object.entries(catalogue)) {
    if (prods.some((p) => norm(p) === n)) return PRODUCT_CLASS_MAP[cls] ?? 'other';
  }
  for (const [cls, prods] of Object.entries(catalogue)) {
    if (prods.some((p) => {
      const pn = norm(p);
      return pn !== '' && (pn.includes(n) || n.includes(pn));
    })) return PRODUCT_CLASS_MAP[cls] ?? 'other';
  }
  return 'other';
}

export function PipelineCreate() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const mutations = usePipelineDealMutations();

  // ── Core form state ──────────────────────────────────────────────────

  const [clientName,  setClientName]  = useState('');
  const [config,      setConfig]      = useState<PipelineConfig | null>(null);
  const [clientType,  setClientType]  = useState<string>('');
  const [segment,     setSegment]     = useState<string>('');
  const [sector,      setSector]      = useState<string>('');
  const [currency,    setCurrency]    = useState<string>('KES');
  const [mouId,       setMouId]       = useState<string>('');     // Individual: selected MOU id
  const [mouQuery,    setMouQuery]    = useState<string>('');     // MOU picker search filter
  const [mouOpen,     setMouOpen]     = useState<boolean>(false); // MOU dropdown open
  const [otherText,   setOtherText]   = useState<string>('');     // free text when 'Other' chosen
  const SENTINEL_OTHER = '__OTHER__';
  const [isNtb,       setIsNtb]       = useState(false);
  const [accountNumber, setAccountNumber] = useState('');

  // γ2: Tracks the CBS customer picked via the autofill dropdown.
  // null means no autofill match (free-text fallback). The picked
  // customer drives the "✓ matched in CBS" badge under the input
  // and lets us derive isNtb=false automatically.
  const [pickedCustomer, setPickedCustomer] = useState<CbsCustomer | null>(null);

  // δ2: Direct CIF entry. Separate from pickedCustomer so users who
  // KNOW the CIF can type it without name-searching first. Auto-populated
  // when user picks a customer via the name dropdown. The "Fetch" button
  // does a GET /api/cbs/customers/{cif} lookup and autofills the form
  // from the returned customer record.
  const [clientCif,     setClientCif]     = useState<string>('');
  const [cifLookupLoading, setCifLookupLoading] = useState<boolean>(false);
  const [cifLookupError,   setCifLookupError]   = useState<string | null>(null);

  const [category,    setCategory]    = useState<PipelineCategory>('Loan');
  const [productType, setProductType] = useState('');
  const [productOther, setProductOther] = useState(false);
  const [dealValue,   setDealValue]   = useState<string>('');     // string so input keeps cursor position
  const [stage,       setStage]       = useState<string>('Lead');
  const [probability, setProbability] = useState<number>(10);     // percent 0..100

  const [nextAction,     setNextAction]     = useState('');
  const [nextActionDate, setNextActionDate] = useState('');
  const [expectedClose,  setExpectedClose]  = useState('');
  const [source,         setSource]         = useState<string>('Existing relationship');
  const [notes,          setNotes]          = useState('');

  // ── Conflict resolution state ────────────────────────────────────────

  const [hasConflict, setHasConflict] = useState(false);
  const [portfolioOwnerCode, setPortfolioOwnerCode] = useState('');
  const [portfolioOwnerName, setPortfolioOwnerName] = useState('');
  const [conflictPath,       setConflictPath]       = useState<ConflictPath>('seek_permission');

  // P2: CBS portfolio-owner auto-detection (existing customers). detectedOwner
  // holds the last lookup; the effect below auto-fills the conflict fields.
  const [detectedOwner, setDetectedOwner] = useState<CustomerPortfolioOwner | null>(null);
  const [ownerDetecting, setOwnerDetecting] = useState(false);
  const [referredTo,         setReferredTo]         = useState('');     // refer path only
  const [referralNote,       setReferralNote]       = useState('');     // refer path only

  // First-class "refer to a colleague" mode on the create page. When on, the
  // form collapses to client + recipient + note; deal-detail fields are hidden
  // and not required (the recipient completes the deal once they accept).
  const [referMode,      setReferMode]      = useState(() => {
    try { return new URLSearchParams(window.location.search).get('refer') === '1'; }
    catch { return false; }
  });
  const [referRecipient, setReferRecipient] = useState<StaffMember | null>(null);
  const [overrideNote,       setOverrideNote]       = useState('');     // override path only

  // ── Submit state ─────────────────────────────────────────────────────
  //
  // β5.0 polish: replaced single submitError with two state slices so we
  // can render field-level errors inline AND a banner for non-field
  // errors (network/server failures). Pattern:
  //   fieldErrors[fieldName] = "human readable message"  → inline + red border
  //   formError              = "human readable message"  → banner at top
  //
  // The banner sits at the TOP of the form (not bottom) so users can
  // see it without scrolling — the bug β5.0 fixes is that the old
  // banner was at the bottom and users missed it entirely.

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError,   setFormError]   = useState<string | null>(null);

  // ── Derived values ───────────────────────────────────────────────────

  // Admin config drives the segment cascade, sectors, and per-class stage
  // flows. Best-effort — the form falls back to legacy defaults if it can't
  // load.
  useEffect(() => {
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) setConfig(c); })
      .catch(() => { /* fall back to category-based stages, empty segments */ });
    return () => { active = false; };
  }, []);

  // Product class drives the stage flow (admin config) — loan vs deposit etc.
  const productClass = useMemo(
    () => classifyProduct(productType, config?.product_catalogue),
    [productType, config],
  );
  const stageOptions = useMemo(() => {
    const flows = config?.stage_flows;
    if (flows && productClass && flows[productClass]?.length) {
      // "Initial stage" excludes terminal stages.
      return flows[productClass].filter(
        (s) => s !== 'Closed Won' && s !== 'Closed Lost',
      );
    }
    return [...INITIAL_STAGES_BY_CATEGORY[category]];   // fallback pre-config
  }, [config, productClass, category]);

  // Client business lines (Consumer / Commercial / CIB) — admin-configurable.
  // The selected type's `field` (mou|sector) drives the third selector.
  const clientTypes = useMemo(
    () => config?.client_types ?? [
      { key: 'Consumer',   label: 'Consumer',                       field: 'mou' as const },
      { key: 'Commercial', label: 'Commercial',                     field: 'sector' as const },
      { key: 'CIB',        label: 'Corporate & Investment Banking', field: 'sector' as const },
    ],
    [config],
  );
  const clientField = useMemo(
    () => clientTypes.find((t) => t.key === clientType)?.field ?? 'sector',
    [clientTypes, clientType],
  );
  const usesSector = clientField === 'sector';

  // Segment cascade off client type; sectors from config.
  const segmentOptions = useMemo(
    () => config?.customer_segments?.[clientType] ?? [],
    [config, clientType],
  );
  // Client-type-aware third field: sector-line -> CBK sectors; mou-line -> MOUs.
  // Both admin-config-driven with an optional "Other…" free-text fallback.
  const businessSectors = useMemo(
    () => config?.business_sectors ?? config?.sectors ?? [],
    [config],
  );
  const individualMous = useMemo(() => config?.individual_mous ?? [], [config]);
  // Searchable picker: filter the (119+) MOU list by the typed query.
  const filteredMous = useMemo(() => {
    const q = mouQuery.trim().toLowerCase();
    if (!q) return individualMous;
    return individualMous.filter((m) =>
      (m.title ?? '').toLowerCase().includes(q) ||
      (m.partner_name ?? '').toLowerCase().includes(q));
  }, [individualMous, mouQuery]);
  const selectedMouTitle = useMemo(
    () => individualMous.find((m) => m.id === mouId)?.title ?? '',
    [individualMous, mouId],
  );

  // Admin-configured mandatory fields (Admin → Configuration). Drives the red
  // asterisks + the extra validation for the optional selection fields (segment
  // / sector / MOU). The four core fields the backend always demands (name /
  // product / value / stage) stay required client-side regardless, so the form
  // can't submit a deal the API would reject.
  const requiredFields = useMemo(
    () => config?.required_fields ?? ['client_name', 'product_type', 'deal_value', 'stage'],
    [config],
  );
  const isReq = (key: string): boolean => requiredFields.includes(key);
  const reqStar = (key: string) => (isReq(key) ? <RedStar /> : null);
  const allowOther = usesSector
    ? (config?.allow_other_sector ?? true)
    : false;  // consumer MOU: no "Other" escape — must pick a listed MOU partner

  // Once config loads, default the client type to the first configured line.
  useEffect(() => {
    if (!clientType && clientTypes.length) setClientType(clientTypes[0].key);
  }, [clientTypes, clientType]);

  // Map the CBS-derived legacy customer type to a configured client-type key.
  const legacyToTypeKey = (legacy: 'Individual' | 'Business'): string => {
    const wantField = legacy === 'Individual' ? 'mou' : 'sector';
    return clientTypes.find((t) => t.field === wantField)?.key
      ?? clientTypes[0]?.key ?? '';
  };

  // Reset the third-field selections when the client type flips, so a stale
  // sector doesn't ride along on a consumer deal (or a stale MOU on a business one).
  useEffect(() => {
    setSector('');
    setMouId('');
    setOtherText('');
  }, [clientType]);

  // Resolve what the client-type-aware third field contributes to the payload.
  const thirdField = useMemo(() => {
    if (usesSector) {
      const s = sector === SENTINEL_OTHER ? otherText.trim() : sector;
      return { sector: s || undefined, mou_id: undefined as string | undefined,
               mou_title: undefined as string | undefined };
    }
    const isOther = mouId === SENTINEL_OTHER;
    return {
      sector: undefined as string | undefined,
      mou_id: isOther || !mouId ? undefined : mouId,
      mou_title: isOther
        ? (otherText.trim() || undefined)
        : individualMous.find((m) => m.id === mouId)?.title,
    };
  }, [usesSector, sector, mouId, otherText, individualMous]);

  // Currency options come from the admin-maintained FX table (active rates),
  // not a hardcoded list — so extending to other Ecobank affiliates or
  // cross-border customers is an admin action, never a code change. KES (base)
  // is always offered even before any FX rate is configured.
  const { rates: fxRates } = useFxRates(true);
  const currencyOptions = useMemo(() => {
    const set = new Set<string>(['KES']);
    for (const r of fxRates) if (r.currency) set.add(r.currency.toUpperCase());
    // KES (local), then the priority trade currencies USD + CNY, then the rest
    // (EcoBank's African footprint) alphabetically.
    const PRIORITY = ['KES', 'USD', 'CNY'];
    return Array.from(set).sort((a, b) => {
      const ia = PRIORITY.indexOf(a);
      const ib = PRIORITY.indexOf(b);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      return a.localeCompare(b);
    });
  }, [fxRates]);
  const selectedRate = useMemo(
    () => (currency === 'KES' ? 1 : fxRates.find((r) => r.currency?.toUpperCase() === currency)?.rate_to_kes),
    [currency, fxRates],
  );

  const productSuggestions = useMemo(() => COMMON_PRODUCTS_BY_CATEGORY[category], [category]);
  // Products offered in the dropdown — sourced from the admin product_catalogue,
  // filtered to the classes that belong to the selected category; falls back to
  // the built-in per-category list if the catalogue is empty.
  const PRODUCT_OTHER = '__other__';
  const productOptions = useMemo(() => {
    const cat = config?.product_catalogue;
    const want: Record<string, ProductClass[]> = {
      Loan: ['asset'], Deposit: ['liability'], Account: ['liability', 'other'],
    };
    const buckets = want[category] ?? ['asset', 'liability', 'insurance', 'other'];
    // P4a: a product whose flow declares client_types is offered ONLY to those
    // client types; an empty (or absent) client_types means offered to all.
    const flows = config?.product_flows ?? {};
    const offeredToClient = (product: string): boolean => {
      const cts = flows[product]?.client_types;
      if (!cts || cts.length === 0) return true;       // all client types
      return !clientType || cts.includes(clientType);
    };
    if (cat) {
      const out: string[] = [];
      for (const [cls, prods] of Object.entries(cat)) {
        if (buckets.includes(PRODUCT_CLASS_MAP[cls] ?? 'other')) {
          out.push(...prods.filter(offeredToClient));
        }
      }
      if (out.length) return Array.from(new Set(out));
    }
    return productSuggestions;
  }, [config, category, clientType, productSuggestions]);
  const dealValueNum       = useMemo(() => {
    const n = Number(String(dealValue).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [dealValue]);

  // Override note is required when conflictPath === 'override' AND user has conflict
  const overrideNoteTooShort = hasConflict && conflictPath === 'override'
    && overrideNote.trim().length < MIN_OVERRIDE_NOTE_LEN;

  // When category changes, ensure stage is valid for the new category.
  // β5.1: AUTO-UPDATE stage to the first option for the new category.
  // β3 originally chose NOT to auto-update ("let user see change explicitly")
  // but that creates a confusing failure mode where the dropdown LOOKS
  // filled with a valid-seeming value (e.g. "Lead") but is invalid for
  // the current category, and submit fails with a "Stage X not valid for
  // Y pipeline" error that users find confusing because the field appears
  // filled. Auto-update eliminates that failure entirely.
  const stageIsValidForCategory = stageOptions.includes(stage);

  useEffect(() => {
    if (!stageOptions.includes(stage)) {
      setStage(stageOptions[0] ?? 'Lead');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, productClass, stageOptions]);

  // Clear segment when it no longer fits the selected client type.
  useEffect(() => {
    if (segment && !segmentOptions.includes(segment)) setSegment('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientType, segmentOptions]);

  // P2: when an existing customer is picked, look up their mapped portfolio
  // owner from CBS. If the customer belongs to a DIFFERENT RM, auto-flag the
  // conflict and pre-fill the owner so the deal can be referred for a nod.
  // If the current user owns the portfolio (or it's unmapped), no conflict.
  useEffect(() => {
    const cif = pickedCustomer?.cif?.trim();
    if (!cif) { setDetectedOwner(null); return; }
    let cancelled = false;
    setOwnerDetecting(true);
    fetchCustomerPortfolioOwner(cif)
      .then((po) => {
        if (cancelled) return;
        setDetectedOwner(po);
        const me = (user?.staff_code || '').trim();
        if (po.is_mapped && po.portfolio_owner_code && po.portfolio_owner_code !== me) {
          setHasConflict(true);
          setPortfolioOwnerCode(po.portfolio_owner_code);
          setPortfolioOwnerName(po.portfolio_owner_name || '');
          setConflictPath('refer');
        } else {
          setHasConflict(false);
          setPortfolioOwnerCode('');
          setPortfolioOwnerName('');
        }
      })
      .catch(() => { if (!cancelled) setDetectedOwner(null); })
      .finally(() => { if (!cancelled) setOwnerDetecting(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedCustomer?.cif, user?.staff_code]);

  // ── Live field error clearing (β5.1) ─────────────────────────────────
  //
  // When a user starts typing in a field that's currently flagged red,
  // clear that field's error immediately — don't wait for re-submit.
  // Without this, users see a red field, fix it, and the red persists
  // until they hit Submit again, which feels broken.
  const clearFieldError = (key: string) => {
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  // δ2 (2026-06-12): direct CIF lookup. User types a CIF in the
  // "Client CIF" input and clicks "Fetch from CBS" (or presses Enter).
  // We GET /api/cbs/customers/{cif}; on success we autofill clientName,
  // clientType, pickedCustomer, isNtb (same shape as picking from the
  // name dropdown). 404 surfaces as an error message under the input.
  const onFetchCif = async () => {
    const cif = clientCif.trim();
    if (!cif) {
      setCifLookupError('Enter a CIF to fetch.');
      return;
    }
    setCifLookupLoading(true);
    setCifLookupError(null);
    try {
      const resp = await fetchCbsCustomer(cif);
      const customer = resp.customer;
      // Mirror the onCustomerPicked branch from the name-search dropdown
      setPickedCustomer(customer);
      setClientName(customer.full_name);
      setClientType(legacyToTypeKey(segmentToCustomerType(customer.segment)));
      setIsNtb(false);
      setClientCif(customer.cif);
      clearFieldError('clientName');
      toast({
        tone: 'success',
        message: `✓ Customer found: ${customer.full_name}`,
      });
    } catch (e) {
      if (e instanceof ApiValidationError) {
        setCifLookupError(e.detail || 'CIF lookup failed.');
      } else {
        const msg = e instanceof Error ? e.message : 'CIF lookup failed.';
        setCifLookupError(msg);
      }
    } finally {
      setCifLookupLoading(false);
    }
  };

  // ── Validation ───────────────────────────────────────────────────────
  //
  // β5.0 polish: returns Record<field-name, message> instead of single
  // string. Collects ALL errors so the user can see every missing field
  // at once rather than fixing them one at a time.
  //
  // Field names match the state variable names (clientName,
  // portfolioOwnerCode, etc.) — the form's per-field rendering uses
  // these as keys when looking up errors.

  const isReferPath = hasConflict && conflictPath === 'refer';

  const validate = (): Record<string, string> => {
    const errors: Record<string, string> = {};

    if (!clientName.trim()) errors.clientName = 'Client name is required.';

    // Refer mode: only the client and the recipient are required; everything
    // else is optional (the recipient completes the deal after accepting).
    if (referMode) {
      if (!referRecipient) errors.referRecipient = 'Choose a colleague to refer this to.';
      return errors;
    }

    if (isReferPath) {
      // Refer path has different required fields
      if (!portfolioOwnerCode.trim()) errors.portfolioOwnerCode = 'Portfolio owner staff code is required for referral.';
      if (!portfolioOwnerName.trim()) errors.portfolioOwnerName = 'Portfolio owner name is required for referral.';
      if (!referredTo.trim())         errors.referredTo         = 'Referred-to name is required.';
      if (user?.staff_code && portfolioOwnerCode.trim() === user.staff_code) {
        errors.portfolioOwnerCode = "You can't refer a deal to yourself.";
      }
      return errors;
    }

    // Standard create path
    // P4: portfolio assignment is mandatory for an EXISTING customer whose CBS
    // portfolio owner is someone else. P2 auto-flags the conflict; if the user
    // has cleared it, they must address it (refer / seek permission / override)
    // rather than silently book a deal against another RM's portfolio.
    const me = (user?.staff_code || '').trim();
    const detectedConflict = !isNtb && !!detectedOwner?.is_mapped
      && !!detectedOwner.portfolio_owner_code
      && detectedOwner.portfolio_owner_code !== me;
    if (detectedConflict && !hasConflict) {
      errors.hasConflict = `This customer is in ${detectedOwner?.portfolio_owner_name || 'another RM'}\u2019s portfolio — choose how to proceed (refer, seek permission, or override).`;
    }

    if (!productType.trim())        errors.productType = 'Product type is required.';
    if (!stage.trim())              errors.stage       = 'Stage is required.';
    if (stage.trim() && !stageIsValidForCategory) {
      errors.stage = `Stage "${stage}" is not valid for ${category} pipeline.`;
    }
    if (!Number.isFinite(dealValueNum) || dealValueNum < 0) {
      errors.dealValue = 'Deal value must be a non-negative number.';
    }

    // Admin-configured mandatory selection fields (layered on the always-on
    // core fields above). Segment / sector / MOU are otherwise optional.
    if (isReq('segment') && segmentOptions.length > 0 && !segment.trim()) {
      errors.segment = 'Segment is required.';
    }
    if (usesSector && isReq('sector') && !sector.trim()) {
      errors.sectorMou = 'CBK sector is required.';
    }
    // Ecobank rule: Consumer deals lend ONLY through an MOU partner, so the
    // MOU is ALWAYS required for a consumer (mou-field) deal — not contingent on
    // admin required_fields config — and the "Other" escape is not permitted.
    if (!usesSector) {
      if (!mouId.trim()) {
        errors.sectorMou = 'An MOU partner is required for consumer deals.';
      } else if (mouId === SENTINEL_OTHER) {
        errors.sectorMou = 'Consumer deals must use a listed MOU partner (no "Other").';
      }
    }

    if (hasConflict) {
      if (!portfolioOwnerCode.trim()) errors.portfolioOwnerCode = 'Portfolio owner staff code is required.';
      if (!portfolioOwnerName.trim()) errors.portfolioOwnerName = 'Portfolio owner name is required.';
      if (user?.staff_code && portfolioOwnerCode.trim() === user.staff_code) {
        errors.portfolioOwnerCode = 'Portfolio owner cannot be yourself — uncheck conflict if you own this portfolio.';
      }
      if (conflictPath === 'override' && overrideNote.trim().length < MIN_OVERRIDE_NOTE_LEN) {
        errors.overrideNote = `Manager override note must be at least ${MIN_OVERRIDE_NOTE_LEN} characters (current: ${overrideNote.trim().length}).`;
      }
    }
    return errors;
  };

  // ── Server error → field mapping ────────────────────────────────────
  //
  // β5.0 polish: try to map server detail strings back to specific
  // fields. Backend validators in utils/api_pipeline_mutations.py
  // emit messages like "Missing required field: client_name". When
  // we recognise the snake_case field, map it to the camelCase state
  // variable and set a fieldError. Otherwise fall back to the banner.

  const SERVER_FIELD_MAP: Record<string, string> = {
    client_name:          'clientName',
    staff_code:           'clientName',   // shouldn't happen — we set this
    staff_name:           'clientName',   // shouldn't happen — we set this
    deal_value:           'dealValue',
    product_type:         'productType',
    stage:                'stage',
    portfolio_owner_code: 'portfolioOwnerCode',
    portfolio_owner_name: 'portfolioOwnerName',
    referred_to:          'referredTo',
    manager_override_note: 'overrideNote',
  };

  const parseServerError = (serverDetail: string): { fieldKey: string | null; message: string } => {
    if (!serverDetail) return { fieldKey: null, message: 'Submission failed.' };
    // Match "Missing required field: X" pattern
    const m1 = serverDetail.match(/Missing required field:\s*(\w+)/i);
    if (m1 && SERVER_FIELD_MAP[m1[1].toLowerCase()]) {
      return { fieldKey: SERVER_FIELD_MAP[m1[1].toLowerCase()], message: serverDetail };
    }
    // Match "manager_override_note required" pattern (α5 override semantics)
    if (/manager_override_note/i.test(serverDetail)) {
      return { fieldKey: 'overrideNote', message: serverDetail };
    }
    // Match "portfolio_owner_code" mentions
    if (/portfolio_owner_code/i.test(serverDetail)) {
      return { fieldKey: 'portfolioOwnerCode', message: serverDetail };
    }
    return { fieldKey: null, message: serverDetail };
  };

  // ── Scroll-to-error helper ──────────────────────────────────────────
  //
  // β5.0 polish: after submit fails, scroll the first errored field
  // into view and focus it. Uses the data-field attr added to each
  // input wrapper. If the field can't be found, scroll to the form
  // top so the banner is visible.

  const scrollToFirstError = (errors: Record<string, string>) => {
    const firstField = Object.keys(errors)[0];
    if (!firstField) return;
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>(`[data-field="${firstField}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Try to focus the first focusable descendant
        const focusable = el.querySelector<HTMLElement>('input, textarea, select');
        if (focusable) focusable.focus({ preventScroll: true });
      } else {
        // Fall back: scroll to top so banner is visible
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }, 50);
  };

  // ── Submit ───────────────────────────────────────────────────────────

  const onSubmit = async () => {
    // Reset any previous error state
    setFormError(null);
    setFieldErrors({});

    // Client-side validation: collect all errors
    const localErrors = validate();
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      // Toast in case user scrolled past the banner
      toast({
        tone: 'danger',
        message: `Please fix ${Object.keys(localErrors).length} issue${Object.keys(localErrors).length > 1 ? 's' : ''} in the form.`,
      });
      scrollToFirstError(localErrors);
      return;
    }

    // Guard against missing user identity (shouldn't happen given the
    // route is ProtectedRoute requireAuth, but type system needs it)
    if (!user?.staff_code || !user?.full_name) {
      setFormError('Your user identity is not loaded. Try refreshing the page.');
      toast({ tone: 'danger', message: 'User identity not loaded — please refresh.' });
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    // ── Refer mode: first-class "refer to a colleague" from create ──────
    if (referMode && referRecipient) {
      const body: ReferDealRequest = {
        client_name:           clientName.trim(),
        staff_code:            user.staff_code,
        staff_name:            user.full_name,
        portfolio_owner_code:  referRecipient.staff_code,
        portfolio_owner_name:  referRecipient.name,
        referred_to:           referRecipient.name,
        referral_note:         referralNote.trim() || undefined,
      };
      const result = await mutations.refer(body);
      if (result.ok) {
        toast({
          tone: 'success',
          message: `Deal referred to ${referRecipient.name} for their acceptance — it stays pending until they accept the nod.`,
        });
        navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
      } else {
        const parsed = parseServerError(result.error);
        if (parsed.fieldKey) {
          setFieldErrors({ [parsed.fieldKey]: parsed.message });
          scrollToFirstError({ [parsed.fieldKey]: parsed.message });
        } else {
          setFormError(parsed.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        toast({ tone: 'danger', message: parsed.message });
      }
      return;
    }

    // ── Refer path: separate endpoint ──────────────────────────────────
    if (isReferPath) {
      const body: ReferDealRequest = {
        client_name:           clientName.trim(),
        staff_code:            user.staff_code,
        staff_name:            user.full_name,
        portfolio_owner_code:  portfolioOwnerCode.trim(),
        portfolio_owner_name:  portfolioOwnerName.trim(),
        referred_to:           referredTo.trim(),
        referral_note:         referralNote.trim() || undefined,
        account_number:        accountNumber.trim() || undefined,
        // Note: unit not sent from client — UserIdentity surfaces
        // department, not unit. Server can resolve unit from staff_code
        // if needed (the create endpoint already does this for other
        // ownership fields).
      };
      const result = await mutations.refer(body);
      if (result.ok) {
        toast({
          tone: 'success',
          message: `Deal referred to ${referredTo.trim()} for their acceptance — it stays pending until they accept the nod.`,
        });
        navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
      } else {
        // Server validation failure — try to map to a field
        const parsed = parseServerError(result.error);
        if (parsed.fieldKey) {
          setFieldErrors({ [parsed.fieldKey]: parsed.message });
          scrollToFirstError({ [parsed.fieldKey]: parsed.message });
        } else {
          setFormError(parsed.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        toast({ tone: 'danger', message: parsed.message });
      }
      return;
    }

    // ── Standard create path (with optional conflict fields) ───────────
    const body: CreateDealRequest = {
      client_name:  clientName.trim(),
      staff_code:   user.staff_code,
      staff_name:   user.full_name,
      deal_value:   dealValueNum,
      product_type: productType.trim(),
      stage:        stage,

      // Optional
      client_type:        clientType,
      currency:           currency || 'KES',
      segment:            segment || undefined,
      sector:             thirdField.sector,
      mou_id:             thirdField.mou_id,
      mou_title:          thirdField.mou_title,
      client_cif:         clientCif.trim() || undefined,  // δ2: persist CIF when known
      is_ntb:             isNtb,
      pipeline_category:  category,
      probability:        probability / 100,
      next_action:        nextAction.trim() || undefined,
      next_action_date:   nextActionDate || undefined,
      expected_close:     expectedClose  || undefined,
      notes:              notes.trim() || undefined,
      source:             source,
      // Note: unit not sent — UserIdentity has department but not unit.
      // Server resolves unit from staff_code if needed.
      account_number:     !isNtb && accountNumber.trim() ? accountNumber.trim() : undefined,
    };

    // ── Apply conflict resolution to body ─────────────────────────────
    if (hasConflict) {
      body.portfolio_owner_code = portfolioOwnerCode.trim();
      body.portfolio_owner_name = portfolioOwnerName.trim();

      if (conflictPath === 'seek_permission') {
        // BSC credit goes to portfolio owner. Backend sees this as
        // seek-permission semantics — NO override note required.
        body.bsc_credit_to = portfolioOwnerName.trim();
      } else if (conflictPath === 'override') {
        // BSC credit goes to caller. Backend detects override semantics
        // and REQUIRES manager_override_note (≥10 chars).
        body.bsc_credit_to          = user.full_name;
        body.manager_override_note  = overrideNote.trim();
      }
    }

    const result = await mutations.create(body);
    if (result.ok) {
      toast({ tone: 'success', message: 'Deal created.' });
      navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
    } else {
      // Server validation failure — try to map to a field
      const parsed = parseServerError(result.error);
      if (parsed.fieldKey) {
        setFieldErrors({ [parsed.fieldKey]: parsed.message });
        scrollToFirstError({ [parsed.fieldKey]: parsed.message });
      } else {
        setFormError(parsed.message);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
      toast({ tone: 'danger', message: parsed.message });
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="New Deal"
        breadcrumbs={[
          { label: 'A2Z Sales Pro', to: '/pipeline' },
          { label: 'New deal' },
        ]}
        subtitle="Capture a lead — customer, classification, value, and ownership."
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline')}>
            ← Back to pipeline
          </Button>
        }
      />

      <main className="max-w-6xl mx-auto px-6 pt-4 pb-8">
        {/* Mode toggle: build a full deal, or refer a lead to a colleague. */}
        <div className="mb-4 inline-flex rounded-lg border border-gray-200 bg-white p-1 text-sm">
          <button
            type="button"
            onClick={() => setReferMode(false)}
            className={`px-4 py-1.5 rounded-md transition ${!referMode ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Create a deal
          </button>
          <button
            type="button"
            onClick={() => setReferMode(true)}
            className={`px-4 py-1.5 rounded-md transition ${referMode ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Refer to a colleague
          </button>
        </div>

        {/* ─────────── Error summary banner (β5.0 polish) ───────────
            Renders at the top so users see it without scrolling.
            Shows either:
              - formError (banner-level: network/server/identity errors), OR
              - a summary count of fieldErrors with a "review fields"
                hint, since each field also shows its own inline message
        */}
        {(formError || Object.keys(fieldErrors).length > 0) && (
          <div
            role="alert"
            aria-live="assertive"
            className="mb-4 px-4 py-3 rounded-md bg-red-50 border-l-4 border-red-500 text-sm text-red-900 shadow-sm"
          >
            {formError ? (
              <div>
                <div className="font-semibold mb-0.5">Submission failed</div>
                <div>{formError}</div>
              </div>
            ) : (
              <div>
                <div className="font-semibold mb-0.5">
                  Please fix {Object.keys(fieldErrors).length} field
                  {Object.keys(fieldErrors).length > 1 ? 's' : ''} below
                </div>
                <div className="text-xs">
                  Each problem is highlighted in red next to the relevant input.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─────────── Form sections (2-up on wide screens) ─────────── */}
        <div className="grid lg:grid-cols-2 gap-5 items-start">
        {/* ─────────── Customer section ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Customer</h2>
            <span className="text-xs text-gray-400">Who is this deal for?</span>
          </Card.Header>
          <Card.Body>
            {/* Relationship status FIRST — drives whether a CBS CIF lookup is
                offered (existing customer) or the form is filled fresh (NTB). */}
            <div className="mb-4">
              <label className="text-sm font-medium text-gray-700">
                Relationship status{reqStar('relationship_status')}
              </label>
              <select
                value={isNtb ? 'ntb' : 'existing'}
                onChange={(e) => setIsNtb(e.target.value === 'ntb')}
                disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option value="existing">Existing customer (has CBS relationship)</option>
                <option value="ntb">New to Bank (NTB) — first-time customer</option>
              </select>
            </div>

            {/* CIF lookup — only meaningful for an existing (in-CBS) customer. */}
            {!isNtb && (
            <div className="mb-4" data-field="clientCif">
              <label className="text-sm font-medium text-gray-700">
                Client CIF (to fetch from CBS)
              </label>
              <div className="flex gap-2 mt-1">
                <input
                  type="text"
                  value={clientCif}
                  onChange={(e) => {
                    setClientCif(e.target.value);
                    if (cifLookupError) setCifLookupError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && clientCif.trim() && !cifLookupLoading) {
                      e.preventDefault();
                      void onFetchCif();
                    }
                  }}
                  placeholder="e.g. 100123456"
                  disabled={mutations.loading || cifLookupLoading}
                  autoComplete="off"
                  className="flex-1 h-10 px-3 rounded-md border border-gray-300 bg-white text-sm font-mono focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                />
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => void onFetchCif()}
                  disabled={!clientCif.trim() || mutations.loading || cifLookupLoading}
                >
                  {cifLookupLoading ? 'Fetching…' : 'Fetch from CBS'}
                </Button>
              </div>
              {cifLookupError && (
                <div className="mt-1 text-xs text-red-700">{cifLookupError}</div>
              )}
              {!cifLookupError && pickedCustomer && clientCif === pickedCustomer.cif && (
                <div className="mt-1 text-xs text-green-700">
                  ✓ CIF matches picked customer
                </div>
              )}
            </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div data-field="clientName">
                <CustomerSearchInput
                  label={<>Client name <RedStar /></>}
                  placeholder="Type a name (min 3 chars) to search CBS, or enter free text"
                  value={clientName}
                  onChange={(v) => { setClientName(v); clearFieldError('clientName'); }}
                  onCustomerPicked={(c) => {
                    // γ2 autofill — when user picks from CBS dropdown,
                    // populate related fields automatically.
                    setPickedCustomer(c);
                    setClientType(legacyToTypeKey(segmentToCustomerType(c.segment)));
                    // Customer is in CBS, so by definition not New-To-Bank.
                    setIsNtb(false);
                    // δ2: also capture the CIF so it persists on the deal.
                    setClientCif(c.cif);
                    setCifLookupError(null);
                    clearFieldError('clientName');
                  }}
                  onCustomerCleared={() => setPickedCustomer(null)}
                  pickedCustomer={pickedCustomer}
                  disabled={mutations.loading}
                  error={fieldErrors.clientName}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Customer type{reqStar('client_type')}
                </label>
                <select
                  value={clientType}
                  onChange={(e) => setClientType(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {clientTypes.map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div data-field="segment">
                <label className="text-sm font-medium text-gray-700">
                  Segment{reqStar('segment')}
                </label>
                <select
                  value={segment}
                  onChange={(e) => { setSegment(e.target.value); clearFieldError('segment'); }}
                  disabled={mutations.loading || segmentOptions.length === 0}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  <option value="">
                    {segmentOptions.length === 0 ? '—' : `Select ${clientType.toLowerCase()} segment`}
                  </option>
                  {segmentOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {fieldErrors.segment && (
                  <p className="text-xs text-red-700 mt-1">{fieldErrors.segment}</p>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Currency{reqStar('currency')}
                </label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {currencyOptions.map((c) => (
                    <option key={c} value={c}>{c}{c === 'KES' ? ' (local)' : ''}</option>
                  ))}
                </select>
                {currency !== 'KES' && (
                  <p className="text-xs text-gray-500 mt-1">
                    {selectedRate
                      ? `FCY · ≈ KES ${(dealValueNum * selectedRate).toLocaleString(undefined, { maximumFractionDigits: 0 })} at ${selectedRate}/${currency}`
                      : `FCY · no admin FX rate set for ${currency} yet`}
                  </p>
                )}
              </div>
              <div data-field="sectorMou">
                <label className="text-sm font-medium text-gray-700">
                  {usesSector
                    ? <>Sector (CBK){reqStar('sector')}</>
                    : <>Partnership / MOU<RedStar /></>}
                </label>
                {usesSector ? (
                  <select
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    disabled={mutations.loading}
                    className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  >
                    <option value="">Select CBK sector (optional)</option>
                    {businessSectors.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                    {allowOther && <option value={SENTINEL_OTHER}>Other…</option>}
                  </select>
                ) : (
                  <div className="relative">
                    <input
                      type="text"
                      value={mouOpen ? mouQuery : selectedMouTitle}
                      placeholder="Search and select an MOU partner (required)"
                      disabled={mutations.loading}
                      autoComplete="off"
                      onFocus={() => { setMouOpen(true); setMouQuery(''); }}
                      onChange={(e) => { setMouQuery(e.target.value); setMouOpen(true); }}
                      onBlur={() => { window.setTimeout(() => setMouOpen(false), 120); }}
                      className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                    />
                    {mouOpen && (
                      <ul className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
                        {filteredMous.length === 0 ? (
                          <li className="px-3 py-2 text-sm text-gray-500">
                            No partner matches “{mouQuery}”.
                          </li>
                        ) : (
                          filteredMous.map((m) => (
                            <li key={m.id}>
                              <button
                                type="button"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  setMouId(m.id);
                                  setMouQuery('');
                                  setMouOpen(false);
                                }}
                                className={`w-full text-left px-3 py-2 text-sm hover:bg-brand-primary/10 ${m.id === mouId ? 'bg-brand-primary/5 font-medium' : ''}`}
                              >
                                {m.title}
                              </button>
                            </li>
                          ))
                        )}
                      </ul>
                    )}
                  </div>
                )}
                {(sector === SENTINEL_OTHER || mouId === SENTINEL_OTHER) && (
                  <input
                    type="text"
                    value={otherText}
                    onChange={(e) => setOtherText(e.target.value)}
                    disabled={mutations.loading}
                    placeholder={usesSector ? 'Specify sector' : 'Specify partner / MOU'}
                    className="mt-2 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  />
                )}
                {fieldErrors.sectorMou && (
                  <p className="text-xs text-red-700 mt-1">{fieldErrors.sectorMou}</p>
                )}
              </div>
              {!isNtb && (
                <Input
                  label="Account number / CIF (optional)"
                  placeholder="e.g. ECO0123456789 or 100456789"
                  value={accountNumber}
                  onChange={(e) => setAccountNumber(e.target.value)}
                  disabled={mutations.loading}
                />
              )}
            </div>
          </Card.Body>
        </Card>

        {referMode && (
          <Card stripe="accent">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Refer to a colleague</h2>
              <span className="text-xs text-gray-400">Recipient + note</span>
            </Card.Header>
            <Card.Body>
              <p className="text-sm text-gray-600 mb-3">
                Hand this lead to a colleague — pick their segment, then the person.
                Only the client name and recipient are required; they complete the
                deal once they accept it.
              </p>
              <StaffPicker value={referRecipient} onChange={setReferRecipient} />
              {fieldErrors.referRecipient && (
                <p className="text-xs text-red-600 mt-2">{fieldErrors.referRecipient}</p>
              )}
              <div className="mt-3">
                <Input
                  label="Note (optional)"
                  placeholder="Why you're referring this"
                  value={referralNote}
                  onChange={(e) => setReferralNote(e.target.value)}
                  disabled={mutations.loading}
                />
              </div>
            </Card.Body>
          </Card>
        )}

        {!referMode && (<>
        {/* ─────────── Deal classification + value ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Deal details</h2>
            <span className="text-xs text-gray-400">Classification + value</span>
          </Card.Header>
          <Card.Body>
            <div>
              <label className="text-sm font-medium text-gray-700">Pipeline category <RedStar /></label>
              <select
                value={category}
                onChange={(e) => {
                  const c = e.target.value as PipelineCategory;
                  setCategory(c);
                  if (!INITIAL_STAGES_BY_CATEGORY[c].includes(stage)) {
                    setStage(INITIAL_STAGES_BY_CATEGORY[c][0]);
                  }
                  setProductType('');
                  setProductOther(false);
                }}
                disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
              >
                {PIPELINE_CATEGORIES.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div className="mt-4" data-field="productType">
              <label className="text-sm font-medium text-gray-700">Product type <RedStar /></label>
              <select
                value={productOther ? PRODUCT_OTHER : (productOptions.includes(productType) ? productType : '')}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === PRODUCT_OTHER) { setProductOther(true); setProductType(''); }
                  else { setProductOther(false); setProductType(v); }
                  clearFieldError('productType');
                }}
                disabled={mutations.loading}
                aria-invalid={!!fieldErrors.productType}
                className={`mt-1 w-full h-10 px-3 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 ${
                  fieldErrors.productType
                    ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                    : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                }`}
              >
                <option value="">Select a product…</option>
                {productOptions.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
                <option value={PRODUCT_OTHER}>Other…</option>
              </select>
              {productOther && (
                <input
                  type="text"
                  value={productType}
                  onChange={(e) => { setProductType(e.target.value); clearFieldError('productType'); }}
                  disabled={mutations.loading}
                  placeholder="Specify product"
                  className="mt-2 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                />
              )}
              {fieldErrors.productType && (
                <p className="mt-1 text-xs text-red-700">{fieldErrors.productType}</p>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              <div data-field="dealValue">
                <Input
                  label={category === 'Account'
                    ? <>Number of accounts <RedStar /></>
                    : <>Deal value (KES) <RedStar /></>}
                  placeholder={category === 'Account' ? 'e.g. 1' : 'e.g. 5000000'}
                  type="number"
                  value={dealValue}
                  onChange={(e) => { setDealValue(e.target.value); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}
                  helper={Number.isFinite(dealValueNum) && dealValueNum > 0
                    ? `${branding?.currency_symbol ?? 'KES'} ${dealValueNum.toLocaleString()}`
                    : undefined}
                  error={fieldErrors.dealValue}
                />
              </div>
              <div data-field="stage">
                <label className="text-sm font-medium text-gray-700">
                  Initial stage <RedStar />
                </label>
                <select
                  value={stage}
                  onChange={(e) => { setStage(e.target.value); clearFieldError('stage'); }}
                  disabled={mutations.loading}
                  aria-invalid={!!fieldErrors.stage}
                  className={`mt-1 w-full h-10 px-3 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 ${
                    fieldErrors.stage
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                      : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                  }`}
                >
                  {stageOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {fieldErrors.stage && (
                  <p className="mt-1 text-xs text-red-700">{fieldErrors.stage}</p>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Probability ({probability}%)
                </label>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={probability}
                  onChange={(e) => setProbability(Number(e.target.value))}
                  disabled={mutations.loading}
                  className="mt-3 w-full"
                />
              </div>
            </div>
          </Card.Body>
        </Card>

        {/* ─────────── Workflow ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Workflow</h2>
            <span className="text-xs text-gray-400">Next steps + source</span>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Input
                label="Next action"
                placeholder="e.g. Send KYC checklist"
                value={nextAction}
                onChange={(e) => setNextAction(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Next action date"
                type="date"
                value={nextActionDate}
                onChange={(e) => setNextActionDate(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Expected close date"
                type="date"
                value={expectedClose}
                onChange={(e) => setExpectedClose(e.target.value)}
                disabled={mutations.loading}
              />
              <div className="md:col-span-2">
                <label className="text-sm font-medium text-gray-700">Lead source</label>
                <select
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                >
                  {SOURCE_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700">
                Notes
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={mutations.loading}
                placeholder="Relationship history, key triggers, urgency..."
                rows={2}
                className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
              />
            </div>
          </Card.Body>
        </Card>

        {/* ─────────── Portfolio conflict resolution ─────────── */}
        <Card stripe={hasConflict ? 'accent' : undefined}>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Portfolio assignment
            </h2>
            <span className="text-xs text-gray-400">
              {hasConflict ? 'α5 conflict resolution' : 'Is this customer already in another RM\u2019s portfolio?'}
            </span>
          </Card.Header>
          <Card.Body>
            <label className="flex items-center gap-3 cursor-pointer" data-field="hasConflict">
              <input
                type="checkbox"
                checked={hasConflict}
                onChange={(e) => { setHasConflict(e.target.checked); if (e.target.checked) clearFieldError('hasConflict'); }}
                disabled={mutations.loading}
                className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary"
              />
              <span className="text-sm text-gray-800">
                This customer is in another RM&rsquo;s portfolio
              </span>
            </label>
            {ownerDetecting && (
              <p className="text-xs text-gray-500 mt-2">Checking portfolio ownership in CBS…</p>
            )}
            {!ownerDetecting && detectedOwner?.is_mapped
              && detectedOwner.portfolio_owner_code
              && detectedOwner.portfolio_owner_code !== (user?.staff_code || '').trim() && (
              <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Auto-detected from CBS: this customer is in{' '}
                <span className="font-semibold">
                  {detectedOwner.portfolio_owner_name || `RM ${detectedOwner.portfolio_owner_code}`}
                </span>
                &rsquo;s portfolio. The deal will be referred to them for a nod.
                {!detectedOwner.owner_in_roster && (
                  <span className="block mt-1 text-amber-700">
                    Note: this owner isn&rsquo;t a recognised system user — confirm the recipient manually.
                  </span>
                )}
              </div>
            )}
            {!ownerDetecting && detectedOwner?.is_mapped
              && detectedOwner.portfolio_owner_code === (user?.staff_code || '').trim() && (
              <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                You are this customer&rsquo;s portfolio owner — no conflict.
              </div>
            )}
            {!ownerDetecting && detectedOwner && !detectedOwner.is_mapped && (
              <p className="text-xs text-gray-500 mt-2">
                No portfolio owner on record for this customer in CBS — mark a conflict manually if needed.
              </p>
            )}
            {!detectedOwner && !ownerDetecting && (
              <p className="text-xs text-gray-500 mt-2">
                Check this if CBS already assigns the customer to a different RM.
                For an existing customer, ownership is detected automatically.
              </p>
            )}
            {fieldErrors.hasConflict && (
              <p className="text-xs text-red-600 mt-2">{fieldErrors.hasConflict}</p>
            )}

            {hasConflict && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div data-field="portfolioOwnerCode">
                  <Input
                    label={<>Portfolio owner staff code <RedStar /></>}
                    placeholder="e.g. 0123"
                    value={portfolioOwnerCode}
                    onChange={(e) => { setPortfolioOwnerCode(e.target.value); clearFieldError('portfolioOwnerCode'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.portfolioOwnerCode}
                  />
                </div>
                <div data-field="portfolioOwnerName">
                  <Input
                    label={<>Portfolio owner name <RedStar /></>}
                    placeholder="e.g. Jane Mwangi"
                    value={portfolioOwnerName}
                    onChange={(e) => { setPortfolioOwnerName(e.target.value); clearFieldError('portfolioOwnerName'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.portfolioOwnerName}
                  />
                </div>
              </div>
            )}

            {hasConflict && (
              <div className="mt-6">
                <label className="text-sm font-medium text-gray-700">
                  How do you want to proceed?
                </label>
                <div className="mt-2 space-y-2">
                  <PathRadio
                    active={conflictPath === 'refer'}
                    onClick={() => setConflictPath('refer')}
                    disabled={mutations.loading}
                    label="Refer to portfolio owner"
                    sub={`Sends the lead to ${portfolioOwnerName || 'the owner'}. They take it from here.`}
                  />
                  <PathRadio
                    active={conflictPath === 'seek_permission'}
                    onClick={() => setConflictPath('seek_permission')}
                    disabled={mutations.loading}
                    label="Seek permission, defer BSC credit"
                    sub={`You'll work the deal; BSC credit on close goes to ${portfolioOwnerName || 'the owner'}. No manager approval required server-side.`}
                  />
                  <PathRadio
                    active={conflictPath === 'override'}
                    onClick={() => setConflictPath('override')}
                    disabled={mutations.loading}
                    label="Override portfolio assignment, take BSC credit"
                    sub={`BSC credit goes to ${user?.full_name ?? 'you'}. Requires manager override note (\u2265 ${MIN_OVERRIDE_NOTE_LEN} chars).`}
                  />
                </div>
              </div>
            )}

            {hasConflict && conflictPath === 'refer' && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div data-field="referredTo">
                  <Input
                    label={<>Referred to (named recipient) <RedStar /></>}
                    placeholder="Usually the portfolio owner"
                    value={referredTo}
                    onChange={(e) => { setReferredTo(e.target.value); clearFieldError('referredTo'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.referredTo}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="text-sm font-medium text-gray-700">
                    Referral note (optional)
                  </label>
                  <textarea
                    value={referralNote}
                    onChange={(e) => setReferralNote(e.target.value)}
                    disabled={mutations.loading}
                    placeholder="Context for the recipient — what does this customer need?"
                    rows={2}
                    className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
                  />
                </div>
              </div>
            )}

            {hasConflict && conflictPath === 'override' && (
              <div className="mt-4" data-field="overrideNote">
                <label className="text-sm font-medium text-gray-700">
                  Manager override note <RedStar /> (min {MIN_OVERRIDE_NOTE_LEN} chars)
                </label>
                <textarea
                  value={overrideNote}
                  onChange={(e) => { setOverrideNote(e.target.value); clearFieldError('overrideNote'); }}
                  disabled={mutations.loading}
                  placeholder="Why is the override appropriate? This is reviewed by management."
                  rows={3}
                  aria-invalid={!!fieldErrors.overrideNote}
                  className={`mt-1 w-full px-3 py-2 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 resize-y ${
                    fieldErrors.overrideNote
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                      : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                  }`}
                />
                {fieldErrors.overrideNote ? (
                  <p className="mt-1 text-xs text-red-700">{fieldErrors.overrideNote}</p>
                ) : overrideNote.length > 0 && overrideNoteTooShort ? (
                  <p className="text-xs text-amber-600 mt-1">
                    {overrideNote.trim().length} / {MIN_OVERRIDE_NOTE_LEN} characters.
                  </p>
                ) : null}
              </div>
            )}
          </Card.Body>
        </Card>
        </>)}
        </div>

        {/* (β5.0 polish: bottom error banner removed.
             Errors now shown at the TOP of the form for visibility
             plus inline next to each errored field.) */}


        <div className="mt-6 flex items-center justify-between gap-4">
          <Button
            variant="ghost"
            size="md"
            onClick={() => navigate('/pipeline')}
            disabled={mutations.loading}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void onSubmit()}
            loading={mutations.loading}
          >
            {(referMode || isReferPath) ? 'Send referral' : 'Create deal'}
          </Button>
        </div>

        {/* Footer */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding?.ip_notice}
        </footer>
      </main>
    </div>
  );
}


// ── Helper components ───────────────────────────────────────────────────

/** Red required-field marker. */
function RedStar() {
  return <span className="text-red-600"> *</span>;
}

interface PathRadioProps {
  active:    boolean;
  onClick:   () => void;
  disabled?: boolean;
  label:     string;
  sub:       React.ReactNode;
}

function PathRadio({ active, onClick, disabled, label, sub }: PathRadioProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left px-4 py-3 rounded-md border transition-colors ${
        active
          ? 'bg-blue-50 border-brand-primary'
          : 'bg-white border-gray-200 hover:border-gray-400'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 h-4 w-4 rounded-full border-2 flex-shrink-0 ${
          active ? 'border-brand-primary bg-brand-primary' : 'border-gray-400'
        }`}>
          {active && <div className="h-1.5 w-1.5 rounded-full bg-white m-auto mt-[3px]" />}
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-gray-900">{label}</div>
          <div className="text-xs text-gray-600 mt-0.5">{sub}</div>
        </div>
      </div>
    </button>
  );
}
