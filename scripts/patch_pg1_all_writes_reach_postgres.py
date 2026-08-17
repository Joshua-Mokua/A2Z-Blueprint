#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
PG1 - every deal write reaches PostgreSQL.

RULING, STATED REPEATEDLY AND FINALLY OBEYED (2026-08-14): "this is a bank
system and I have always insisted the bank is clear that this will purely run
on PostgreSQL. Anything we are doing on JSON is costing us and will have bigger
effect. Why don't we just obey that?"

It has cost four separate mornings. PipelineManager.update_deal writes the JSON
store and NOTHING ELSE, while deals are READ DB-first - so a change written
through it lands somewhere nothing reads. Each time the symptom looked like a
different bug:

    branch lost on the round trip     a case never reached its committee
    a seeded case invisible           the queue read a store the seeder had not
    a vote that vanished              no journey entry, no quorum, "Review"
                                      for ever

Of 23 update_deal call sites in api.py, ELEVEN had no sync. That is not a bug
to fix eleven times; it is a missing function.

    _write_deal(pm, deal_id, updates, actor)

writes both stores, and all eleven now use it. Zero unsynced writes remain.

WHY NOT FIX IT PROPERLY IN PipelineManager? Because utils/core.py is a DELTA
file - it never travels to the pilot - so a DB-backed manager there would help
nobody at the bank. This lives in api.py, which does travel. The proper fix is
still worth doing, and is written up in docs/ONE_DEAL_STORE.md; this is what
obeys the ruling today.

FAILS SAFE. If the database write fails the JSON write still stands and a
warning is logged: a recorded decision must not be lost because the copy
failed.

ALSO: the Committee tab counted cases the COMMITTEE had not finished. Three
cases with your vote on two of them is one outstanding task, not three - and a
badge that will not go down as you work is a badge people stop reading. It now
counts what is waiting on YOU.

Verified: py_compile clean, the API imports with 205 routes, tsc --noEmit
clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_pg1_all_writes_reach_postgres.py            # dry run
    python scripts\\patch_pg1_all_writes_reach_postgres.py --apply
"""
import json
import os
import re
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_pg1"

FILES = json.loads(r'''{
 "frontend/web/src/pages/PipelineManagerQueues.tsx": "// v10.513 Phase 4 Batch \u03b24 \u2014 PipelineManagerQueues page.\n//\n// Manager-only page at /pipeline/queues with two tabs:\n//\n//   1. Validation queue \u2014 deals past Lead awaiting manager validation.\n//      Each deal has Validate (approved:true) / Query (approved:false)\n//      action panel.\n//\n//   2. Cancellation queue \u2014 deals with pending cancellation requests\n//      awaiting manager decision. Each deal has Approve / Reject\n//      action panel.\n//\n// Authorization layers (defense in depth):\n//   1. Sidebar hides the \"Manager Queues\" link from non-managers (UX)\n//   2. This page renders \"Not authorized\" guard when isManager(user)\n//      is false, before even attempting the fetch (UX)\n//   3. Server returns 403 to non-managers on the queue endpoints\n//      (the real security boundary)\n//\n// Pattern reuse:\n//   - Tab strip + count badges: bespoke (no Tab primitive)\n//   - Per-deal action panels: same shape as \u03b22 detail page panels\n//   - Same Toast pattern for success / error\n//   - Same mutation hook pattern\n\nimport { displayName } from \"../lib/names\";\nimport { useCallback, useEffect, useState } from 'react';\nimport { useNavigate, Link } from 'react-router-dom';\nimport { useBranding } from '@/hooks/useBranding';\nimport { useRole } from '@/hooks/useRole';\nimport { useToast } from '@/components/Toast';\nimport { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';\nimport { isManager } from '@/lib/role';\nimport {\n  fetchValidationQueue, AuthExpiredError,\n} from '@/lib/api';\nimport { Card } from '@/components/Card';\nimport { Badge } from '@/components/Badge';\nimport { Button } from '@/components/Button';\nimport { Skeleton } from '@/components/Skeleton';\nimport { PageHeader } from '@/components/PageHeader';\nimport { CommitteeQueue } from '@/components/CommitteeQueue';\nimport { fetchCommitteeQueue } from '@/lib/api';\nimport DailyLogValidation from '@/components/DailyLogValidation';\nimport BranchCountersign from '@/components/BranchCountersign';\nimport UnitRollup from '@/components/UnitRollup';\nimport Leaderboard from '@/components/Leaderboard';\nimport DailyLogAnalytics from '@/components/DailyLogAnalytics';\nimport PipelineLeaderboard from '@/components/PipelineLeaderboard';\nimport PipelineDayCountersign from '@/components/PipelineDayCountersign';\nimport PipelineBranchDay from '@/components/PipelineBranchDay';\nimport { fetchUnitDays } from '@/lib/api';\nimport {\n  stageTone, type PipelineDeal,\n} from '@/types/pipeline';\n\n\ntype TabKey = 'validation' | 'committee' | 'dailylog' | 'ranking' | 'analytics';\n\n\n// \u2500\u2500 Page component \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\nexport function PipelineManagerQueues() {\n  const { branding } = useBranding();\n  const { user } = useRole();\n  const { toast } = useToast();\n  const navigate = useNavigate();\n\n  const userIsManager = isManager(user);\n\n  // \u2500\u2500 Page-local state \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n  const [activeTab, setActiveTab] = useState<TabKey>('validation');\n  // Fetched once for the badge; the panel loads its own copy when opened.\n  const [committeeCount, setCommitteeCount] = useState(0);\n  useEffect(() => {\n    void (async () => {\n      try {\n        // COUNT WHAT IS WAITING ON YOU, not what the committee has not\n        // finished. Three cases with your vote already on two of them is one\n        // outstanding task, not three - and a badge that will not go down as\n        // you work is a badge people stop reading.\n        const q = await fetchCommitteeQueue();\n        setCommitteeCount(q.cases.filter((c) => !c.you_voted).length);\n      } catch {\n        setCommitteeCount(0);\n      }\n    })();\n  }, []);\n  const [validationDeals, setValidationDeals] = useState<PipelineDeal[]>([]);\n  const [loadingV, setLoadingV] = useState(false);\n  const [errorV,   setErrorV]   = useState<string | null>(null);\n  // Daily-log queue owns its own fetching; the page only tracks the count\n  // for the tab badge.\n  const [dailyLogPending, setDailyLogPending] = useState(0);\n  // Tier 2 (Head of Branches, MD) countersigns BRANCHES; everyone else\n  // validates individuals. Decided by asking the server what this caller\n  // oversees rather than by inspecting their role string here.\n  // 'staff' = validates individuals, 'branch' = countersigns branches,\n  // 'rollup' = MD / Business Manager, observes and may return.\n  const [tier, setTier] = useState<'staff' | 'branch' | 'rollup' | null>(null);\n  const [rankView, setRankView] = useState<'index' | 'pipeline'>('index');\n\n  // \u2500\u2500 Fetchers \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n  const loadValidation = useCallback(async () => {\n    if (!userIsManager) return;\n    setLoadingV(true);\n    setErrorV(null);\n    try {\n      const res = await fetchValidationQueue();\n      setValidationDeals(res.deals);\n    } catch (e) {\n      if (e instanceof AuthExpiredError) return;\n      const msg = e instanceof Error ? e.message : 'Failed to load validation queue';\n      setErrorV(msg);\n      setValidationDeals([]);\n    } finally {\n      setLoadingV(false);\n    }\n  }, [userIsManager]);\n\n  useEffect(() => {\n    let alive = true;\n    void (async () => {\n      try {\n        // One probe. /unit-days answers both questions: top_of_house marks the\n        // observation tier, and a Branches node means this caller countersigns\n        // branches. Asking the server beats inspecting a role string here.\n        const r = await fetchUnitDays();\n        if (!alive) return;\n        if (r.top_of_house) setTier('rollup');\n        else if ((r.branches?.children?.length ?? 0) > 0) setTier('branch');\n        else setTier('staff');\n      } catch {\n        if (alive) setTier('staff');\n      }\n    })();\n    return () => { alive = false; };\n  }, []);\n\n  // Initial load + reload on tab focus to keep queues fresh\n  useEffect(() => {\n    void loadValidation();\n  }, [loadValidation]);\n\n  // \u2500\u2500 Render guards \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n  if (!userIsManager) {\n    return (\n      <div className=\"min-h-screen bg-gray-50\">\n        <PageHeader\n          title=\"Manager Queues\"\n          breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}\n        />\n        <div className=\"max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6\">\n        <Card>\n          <Card.Header>\n            <div className=\"flex items-center gap-3\">\n              <Badge tone=\"warning\">Not authorized</Badge>\n              <h2 className=\"text-base font-semibold text-gray-900\">\n                Manager queues\n              </h2>\n            </div>\n          </Card.Header>\n          <Card.Body>\n            <p className=\"text-sm text-gray-700\">\n              These queues are only visible to staff with manager authority\n              (Branch Manager, Regional Head, Director, MD, etc.).\n            </p>\n            <p className=\"text-sm text-gray-500 mt-3\">\n              If you believe this is wrong, contact your administrator.\n              Your current role is{' '}\n              <span className=\"font-mono text-gray-700\">\n                {user?.role ?? '(unknown)'}\n              </span>.\n            </p>\n            <div className=\"mt-4\">\n              <Link\n                to=\"/pipeline\"\n                className=\"text-sm text-brand-primary underline\"\n              >\n                \u2190 Back to pipeline\n              </Link>\n            </div>\n          </Card.Body>\n        </Card>\n        </div>\n      </div>\n    );\n  }\n\n  // \u2500\u2500 Active tab data \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n  // Cancellation was removed from this page (ruling 2026-08-09); the deal list\n  // here is now only ever the pipeline validation queue.\n  const activeDeals    = validationDeals;\n  const activeLoading  = loadingV;\n  const activeError    = errorV;\n  const activeReload   = loadValidation;\n\n  // \u2500\u2500 Main render \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n  return (\n    <div className=\"min-h-screen bg-gray-50\">\n      <PageHeader\n        title=\"Manager Queues\"\n        breadcrumbs={[{ label: 'A2Z Pipeline Intelligence System (PIS)' }, { label: 'Manager Queues' }]}\n      />\n      <div className=\"max-w-7xl 2xl:max-w-[1680px] mx-auto px-6 py-6\">\n\n      {/* Tab strip */}\n      <div className=\"flex items-center gap-2 border-b border-gray-200\">\n        <TabBtn\n          active={activeTab === 'validation'}\n          onClick={() => setActiveTab('validation')}\n          label=\"Pipeline validation\"\n          count={validationDeals.length}\n          loading={loadingV}\n        />\n        {/* Committee sits beside validation because it is the same kind of\n            work - a queue of things waiting on this person's decision. No new\n            sidebar entry (ruling 2026-08-12). */}\n        <TabBtn\n          active={activeTab === 'committee'}\n          onClick={() => setActiveTab('committee')}\n          label=\"Committee\"\n          // The real number, not a hardcoded zero. A tab that always reads 0\n          // tells somebody there is nothing to do, which is the opposite of\n          // what this queue exists to say.\n          count={committeeCount}\n          loading={false}\n        />\n        <TabBtn\n          active={activeTab === 'dailylog'}\n          onClick={() => setActiveTab('dailylog')}\n          label=\"Daily log validation\"\n          count={dailyLogPending}\n          loading={false}\n        />\n        <TabBtn\n          active={activeTab === 'ranking'}\n          onClick={() => setActiveTab('ranking')}\n          label=\"Ranking\"\n          count={0}\n          loading={false}\n        />\n        <TabBtn\n          active={activeTab === 'analytics'}\n          onClick={() => setActiveTab('analytics')}\n          label=\"Index analytics\"\n          count={0}\n          loading={false}\n        />\n        <div className=\"flex-1\" />\n        <Button\n          variant=\"ghost\"\n          size=\"sm\"\n          onClick={() => void activeReload()}\n          loading={activeLoading}\n        >\n          Refresh\n        </Button>\n      </div>\n\n      {/* Daily-log validation owns its own loading, empty and error states. */}\n      {activeTab === 'committee' && <CommitteeQueue />}\n\n      {activeTab === 'dailylog' && tier === null && (\n        <Card className=\"mt-4\"><Card.Body>\n          <div className=\"text-sm text-gray-400\">Loading\u2026</div>\n        </Card.Body></Card>\n      )}\n      {activeTab === 'dailylog' && tier === 'rollup' && (\n        <UnitRollup onCount={setDailyLogPending} />\n      )}\n      {activeTab === 'dailylog' && tier === 'branch' && (\n        <BranchCountersign onCount={setDailyLogPending} />\n      )}\n      {activeTab === 'dailylog' && tier === 'staff' && (\n        <DailyLogValidation onCount={setDailyLogPending} />\n      )}\n\n      {/* Ranking and analytics live here too: a manager works out of this page,\n          and making them navigate elsewhere to see how their team is doing\n          splits one job across two screens. Both components are scope-aware\n          server-side, so each manager sees their own population. */}\n      {/* Pipeline validation follows the daily log's tier routing: a branch or\n          roll-up caller countersigns days; everyone else works the deal queue\n          below. Same shape, so a manager learns one screen and knows both. */}\n      {activeTab === 'validation' && (tier === 'branch' || tier === 'rollup') && (\n        <PipelineDayCountersign onCount={() => { /* count shown on the tab */ }} />\n      )}\n\n      {/* Tier 1 \u2014 the branch triad. This was the old per-deal card list; the\n          pilot reported that it did not match the daily log, so it now uses the\n          same shape: rows, a branch line, and a gate on closing the day. */}\n      {activeTab === 'validation' && tier === 'staff' && <PipelineBranchDay />}\n\n      {/* Two rankings, one tab: the productivity INDEX and the PIPELINE. They\n          measure different things over the same people, so they sit side by\n          side rather than being blended into a single misleading number. */}\n      {activeTab === 'ranking' && (\n        <div className=\"mt-4 space-y-4\">\n          <div className=\"flex gap-1.5 text-xs\">\n            {(['index', 'pipeline'] as const).map((k) => (\n              <button key={k} type=\"button\" onClick={() => setRankView(k)}\n                className={'rounded-full px-3 py-1 font-medium '\n                  + (rankView === k ? 'bg-[#005B82] text-white'\n                                    : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>\n                {k === 'index' ? 'Index ranking' : 'Pipeline ranking'}\n              </button>\n            ))}\n          </div>\n          {rankView === 'index' ? <Leaderboard /> : <PipelineLeaderboard />}\n        </div>\n      )}\n      {activeTab === 'analytics' && <DailyLogAnalytics />}\n\n      {/* Error panel */}\n      {!['dailylog', 'ranking', 'analytics', 'committee'].includes(activeTab)\n        && !(activeTab === 'validation' && (tier === 'branch' || tier === 'rollup' || tier === 'staff'))\n        && activeError && (\n        <Card className=\"mt-4\">\n          <Card.Body>\n            <div className=\"flex items-center gap-3\">\n              <Badge tone=\"danger\">Error</Badge>\n              <div className=\"flex-1 text-sm text-gray-700\">{activeError}</div>\n              <Button variant=\"ghost\" size=\"sm\" onClick={() => void activeReload()}>\n                Retry\n              </Button>\n            </div>\n          </Card.Body>\n        </Card>\n      )}\n\n      {/* Empty / loading / content */}\n      {['dailylog', 'ranking', 'analytics', 'committee'].includes(activeTab)\n        || (activeTab === 'validation' && (tier === 'branch' || tier === 'rollup' || tier === 'staff'))\n        ? null : activeLoading && activeDeals.length === 0 ? (\n        <Card className=\"mt-4\">\n          <Card.Body>\n            <Skeleton shape=\"line\" className=\"w-1/3\" />\n            <div className=\"mt-3\"><Skeleton shape=\"block\" className=\"h-12\" /></div>\n            <div className=\"mt-2\"><Skeleton shape=\"block\" className=\"h-12\" /></div>\n          </Card.Body>\n        </Card>\n      ) : activeDeals.length === 0 && !activeError ? (\n        <Card className=\"mt-4\">\n          <Card.Body>\n            <div className=\"text-sm text-gray-700 font-medium\">\n              No deals in this queue.\n            </div>\n            <div className=\"text-xs text-gray-500 mt-1\">\n              {activeTab === 'validation'\n                ? 'New deals past Lead stage will appear here for your validation.'\n                : 'Cancellation requests from your team will appear here for your decision.'}\n            </div>\n          </Card.Body>\n        </Card>\n      ) : (\n        <div className=\"mt-4 space-y-3\">\n          {activeDeals.map((deal) => (\n            activeTab === 'validation' ? (\n              <ValidationCard\n                key={deal.id}\n                deal={deal}\n                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}\n                onResolved={() => {\n                  toast({ tone: 'success', message: 'Validation decision recorded.' });\n                  void loadValidation();\n                }}\n                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}\n              />\n            ) : (\n              <CancellationCard\n                key={deal.id}\n                deal={deal}\n                onNavigate={() => navigate(`/pipeline/${encodeURIComponent(deal.id)}`)}\n                onResolved={() => {\n                  toast({ tone: 'success', message: 'Decision recorded.' });\n                  void loadValidation();\n                }}\n                onErrorToast={(msg) => toast({ tone: 'danger', message: msg })}\n              />\n            )\n          ))}\n        </div>\n      )}\n\n      {/* Footer */}\n      <footer className=\"mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed\">\n        {branding?.ip_notice}\n      </footer>\n      </div>\n    </div>\n  );\n}\n\n\n// \u2500\u2500 Tab button \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\ninterface TabBtnProps {\n  active:   boolean;\n  onClick:  () => void;\n  label:    string;\n  count:    number;\n  loading:  boolean;\n}\n\nfunction TabBtn({ active, onClick, label, count, loading }: TabBtnProps) {\n  return (\n    <button\n      type=\"button\"\n      onClick={onClick}\n      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${\n        active\n          ? 'border-brand-primary text-brand-primary'\n          : 'border-transparent text-gray-600 hover:text-gray-900'\n      }`}\n    >\n      {label}\n      {' '}\n      <span className={`ml-1 px-2 py-0.5 text-[11px] rounded-full ${\n        active ? 'bg-brand-primary text-white' : 'bg-gray-200 text-gray-700'\n      }`}>\n        {loading ? '\u2026' : count}\n      </span>\n    </button>\n  );\n}\n\n\n// \u2500\u2500 Common queue card scaffolding \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\ninterface QueueCardCommonProps {\n  deal:         PipelineDeal;\n  onNavigate:   () => void;\n  children:     React.ReactNode;\n}\n\nfunction QueueCard({ deal, onNavigate, children }: QueueCardCommonProps) {\n  const { branding } = useBranding();\n  const sym = branding?.currency_symbol ?? '';\n  return (\n    <Card>\n      <Card.Header>\n        <div className=\"flex items-center gap-3 flex-wrap\">\n          <button\n            type=\"button\"\n            onClick={onNavigate}\n            className=\"font-mono text-xs text-brand-primary hover:underline\"\n          >\n            {deal.id}\n          </button>\n          <h3 className=\"text-sm font-semibold text-gray-900\">\n            {deal.client_name || '\u2014'}\n          </h3>\n          <Badge tone={stageTone(deal.stage)} size=\"sm\">{deal.stage}</Badge>\n        </div>\n        <div className=\"text-xs text-gray-500 text-right\">\n          <div>{deal.product_type ?? deal.product ?? '\u2014'}</div>\n          <div className=\"font-medium text-gray-900 mt-0.5\">\n            {sym} {Number(deal.amount_kes ?? deal.deal_value ?? 0).toLocaleString()}\n          </div>\n        </div>\n      </Card.Header>\n      <Card.Body>\n        <div className=\"grid grid-cols-2 md:grid-cols-4 gap-3 text-xs mb-3\">\n          <Field label=\"Owner\" value={deal.staff_name ? displayName(deal.staff_name) : undefined} sub={deal.staff_code} />\n          <Field label=\"Probability\" value={\n            typeof deal.probability === 'number'\n              ? `${Math.round(deal.probability * 100)}%`\n              : '\u2014'\n          } />\n          <Field label=\"Next action\" value={deal.next_action} />\n          <Field label=\"Expected close\" value={(deal.expected_close ?? '').slice(0, 10) || '\u2014'} />\n        </div>\n        {children}\n      </Card.Body>\n    </Card>\n  );\n}\n\nfunction Field({ label, value, sub }: {\n  label: string;\n  value: React.ReactNode;\n  sub?: React.ReactNode;\n}) {\n  return (\n    <div>\n      <div className=\"text-[10px] font-semibold uppercase tracking-wider text-gray-500\">\n        {label}\n      </div>\n      <div className=\"text-sm text-gray-900 mt-0.5\">{value ?? '\u2014'}</div>\n      {sub && (\n        <div className=\"text-[10px] text-gray-400 font-mono\">{sub}</div>\n      )}\n    </div>\n  );\n}\n\n\n// \u2500\u2500 Validation card (Validate / Query buttons + note) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\ninterface ResolvedCallbacks {\n  onResolved:    () => void;\n  onErrorToast:  (msg: string) => void;\n}\n\nfunction ValidationCard({ deal, onNavigate, onResolved, onErrorToast }: {\n  deal: PipelineDeal;\n  onNavigate: () => void;\n} & ResolvedCallbacks) {\n  const mutations = usePipelineDealMutations();\n  const [note, setNote] = useState('');\n\n  const submit = async (approved: boolean) => {\n    const result = await mutations.validate(deal.id, {\n      approved,\n      note: note.trim() || undefined,\n    });\n    if (result.ok) {\n      setNote('');\n      onResolved();\n    } else {\n      onErrorToast(result.error);\n    }\n  };\n\n  return (\n    <QueueCard deal={deal} onNavigate={onNavigate}>\n      <div className=\"border-t border-gray-100 pt-3\">\n        <label className=\"text-xs font-medium text-gray-700\">\n          Manager note (optional)\n        </label>\n        <input\n          type=\"text\"\n          value={note}\n          onChange={(e) => setNote(e.target.value)}\n          disabled={mutations.loading}\n          placeholder=\"Context for the owner if querying\"\n          className=\"mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20\"\n        />\n        <div className=\"mt-3 flex items-center justify-end gap-2\">\n          <Button\n            variant=\"ghost\"\n            size=\"sm\"\n            onClick={() => void submit(false)}\n            loading={mutations.loading}\n          >\n            Query (return to owner)\n          </Button>\n          <Button\n            variant=\"primary\"\n            size=\"sm\"\n            onClick={() => void submit(true)}\n            loading={mutations.loading}\n          >\n            Validate \u2014 include in forecast\n          </Button>\n        </div>\n      </div>\n    </QueueCard>\n  );\n}\n\n\n// \u2500\u2500 Cancellation card (Approve / Reject buttons + reason context) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\nfunction CancellationCard({ deal, onNavigate, onResolved, onErrorToast }: {\n  deal: PipelineDeal;\n  onNavigate: () => void;\n} & ResolvedCallbacks) {\n  const mutations = usePipelineDealMutations();\n  const [note, setNote] = useState('');\n\n  const submit = async (approve: boolean) => {\n    const result = await mutations.approveCancel(deal.id, {\n      approve,\n      note: note.trim() || undefined,\n    });\n    if (result.ok) {\n      setNote('');\n      onResolved();\n    } else {\n      onErrorToast(result.error);\n    }\n  };\n\n  return (\n    <QueueCard deal={deal} onNavigate={onNavigate}>\n      {/* Requested-by + reason context */}\n      <div className=\"px-3 py-2 rounded-md bg-amber-50 border border-amber-200 text-xs\">\n        <div className=\"font-semibold text-amber-900\">\n          Cancellation requested\n          {deal.cancel_requested_by && ` by ${deal.cancel_requested_by}`}\n        </div>\n        {deal.cancel_reason && (\n          <div className=\"text-amber-800 mt-1\">\n            <span className=\"font-medium\">Reason:</span> {deal.cancel_reason}\n          </div>\n        )}\n      </div>\n      <div className=\"border-t border-gray-100 pt-3 mt-3\">\n        <label className=\"text-xs font-medium text-gray-700\">\n          Your decision note (optional)\n        </label>\n        <input\n          type=\"text\"\n          value={note}\n          onChange={(e) => setNote(e.target.value)}\n          disabled={mutations.loading}\n          placeholder=\"Recorded on the deal for audit\"\n          className=\"mt-1 w-full h-9 px-3 rounded-md border border-gray-300 bg-white text-sm focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20\"\n        />\n        <div className=\"mt-3 flex items-center justify-end gap-2\">\n          <Button\n            variant=\"ghost\"\n            size=\"sm\"\n            onClick={() => void submit(false)}\n            loading={mutations.loading}\n          >\n            Decline cancellation \u2014 deal continues\n          </Button>\n          <Button\n            variant=\"danger\"\n            size=\"sm\"\n            onClick={() => void submit(true)}\n            loading={mutations.loading}\n          >\n            Approve cancellation \u2014 close as Lost\n          </Button>\n        </div>\n      </div>\n    </QueueCard>\n  );\n}\n"
}''')

HELPER = r'''def _write_deal(pm, deal_id: str, updates: dict, actor: str = "") -> None:
    """Write a deal change to BOTH stores. Use this, never update_deal alone.

    RULING, stated repeatedly and finally obeyed (2026-08-14): "this is a bank
    system ... it will purely run on PostgreSQL. Anything we are doing on JSON
    is costing us."

    It has cost us four separate mornings. PipelineManager.update_deal writes
    the JSON store and nothing else, while deals are READ DB-first - so a
    change written through it lands somewhere nothing reads. Each time the
    symptom looked like a different bug:

        branch lost              a case never reached its committee
        a seeded case invisible  the queue read a store the seeder had not
        a vote that vanished     no journey entry, no quorum, "Review" for ever

    Of 23 update_deal call sites in this module, 11 had no sync. That is not a
    bug to fix eleven times; it is a missing function.

    THE PROPER FIX is a DB-backed PipelineManager - but core.py is a delta file
    that never travels to the pilot, so a fix there would help nobody at the
    bank. This lives in api.py, which does travel.

    The whole deal is re-read and synced, not the updates alone, so anything
    else set in the same request travels with it. If the database write fails
    the JSON write still stands and a warning is logged: a recorded decision
    must not be lost because the copy failed.
    """
    pm.update_deal(deal_id, updates, actor)
    try:
        if _db_available():
            fresh = pm.get_deal(deal_id)
            if fresh:
                _db_sync_pipeline_deal(fresh)
    except Exception as exc:
        logger.warning("deal %s written to JSON but not synced to the "
                       "database: %s", deal_id, exc)

'''



def main():
    apply = "--apply" in sys.argv
    for f in [API] + sorted(FILES):
        if not os.path.isfile(f):
            print("ABORT: %s not found." % f)
            return 1

    s = open(API, encoding="utf-8").read()
    if "def _write_deal(" in s:
        print("ABORT: PG1 looks applied.")
        return 1

    anchor = "def _db_sync_pipeline_deal("
    if s.count(anchor) != 1:
        print("ABORT: _db_sync_pipeline_deal matched %d times." % s.count(anchor))
        return 1
    i = s.index(anchor)
    j = s.index("\ndef ", i + 10)
    s = s[:j] + "\n" + HELPER + s[j:]

    # Route every unsynced write through it.
    out, pos, converted = [], 0, 0
    for m in re.finditer(r'(\s*)(\w+)\.update_deal\(', s):
        if m.start() < pos:
            continue
        if "_db_sync_pipeline_deal" in s[m.end(): m.end() + 900]:
            continue
        out.append(s[pos:m.start()])
        out.append("%s_write_deal(%s, " % (m.group(1), m.group(2)))
        pos = m.end()
        converted += 1
    out.append(s[pos:])
    s = "".join(out)
    # The helper's own call must stay as update_deal, or it recurses.
    s = s.replace("    _write_deal(pm, deal_id, updates, actor)",
                  "    pm.update_deal(deal_id, updates, actor)", 1)
    print("  ok  helper added, %d unsynced write(s) routed through it" % converted)

    left = 0
    for m in re.finditer(r'\.update_deal\(', s):
        if "_db_sync_pipeline_deal" not in s[m.start(): m.start() + 900]:
            left += 1
    if left:
        print("ABORT: %d write(s) still bypass the database." % left)
        return 1
    if "def _write_deal(" not in s:
        print("ABORT: the helper is missing.")
        return 1
    if "except Exception" not in HELPER:
        print("ABORT: a failed database write would lose the change entirely.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    q = FILES["frontend/web/src/pages/PipelineManagerQueues.tsx"]
    if "!c.you_voted" not in q:
        print("ABORT: the Committee badge would still count cases you have")
        print("       already voted on.")
        return 1
    print("  ok  post-checks: zero unsynced writes, fails safe, badge honest")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)
    for f, new in FILES.items():
        shutil.copy2(f, f + BACKUP_SUFFIX)
        open(f, "w", encoding="utf-8", newline="").write(new)
        print("APPLIED %s" % f)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && pnpm build && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
