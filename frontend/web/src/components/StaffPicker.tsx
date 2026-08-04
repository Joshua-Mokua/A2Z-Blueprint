// StaffPicker — two-step referral recipient picker.
// Step 1: choose a segment (Department). Step 2: pick a person within it (with a
// search box to narrow further). Avoids scrolling the whole 487-person roster.
import { displayName } from "../lib/names";
import { useEffect, useState } from 'react';
import { fetchStaffSegments, searchStaff, type StaffMember, type StaffSegment } from '@/lib/api';

const inputCls =
  'w-full px-3 py-1.5 rounded-md border border-gray-300 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

interface StaffPickerProps {
  branchScope?: string;
  value: StaffMember | null;
  onChange: (member: StaffMember | null) => void;
}

export function StaffPicker({ value, onChange, branchScope }: StaffPickerProps) {
  const [showAll, setShowAll] = useState(false);
  const [segments, setSegments] = useState<StaffSegment[]>([]);
  const [segment, setSegment] = useState('');
  const [q, setQ] = useState('');
  const [results, setResults] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchStaffSegments().then((r) => setSegments(r.segments)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!segment && !q.trim()) { setResults([]); return; }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(() => {
      searchStaff(q.trim(), segment, showAll ? undefined : branchScope)
        .then((r) => { if (!cancelled) setResults(r.staff); })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 200);
    return () => { cancelled = true; clearTimeout(t); };
  }, [segment, q]);

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-brand-primary/30 bg-brand-primary/5 px-3 py-2">
        <div className="min-w-0">
          <div className="text-sm font-medium text-gray-900 truncate">{displayName(value.name, (value as any).display_name)}</div>
          <div className="text-xs text-gray-500">
            {value.staff_code}{value.role ? ` · ${value.role}` : ''}{value.segment ? ` · ${value.segment}` : ''}
          </div>
        </div>
        <button onClick={() => onChange(null)} className="text-xs text-gray-400 hover:text-red-600 shrink-0 ml-3">
          Change
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="grid sm:grid-cols-2 gap-2">
        <select className={inputCls} value={segment} onChange={(e) => setSegment(e.target.value)}>
          <option value="">All segments…</option>
          {segments.map((s) => (
            <option key={s.segment} value={s.segment}>{s.segment} ({s.count})</option>
          ))}
        </select>
        {branchScope && (
          <button type="button" className="mt-1 text-xs text-brand-primary hover:underline"
            onClick={() => setShowAll((v) => !v)}>
            {showAll ? `Filter to ${branchScope}` : "Show all branches"}
          </button>
        )}
        <input className={inputCls} placeholder="Search name or code…"
          value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="max-h-56 overflow-y-auto rounded-md border border-gray-200 divide-y divide-gray-100">
        {loading && <div className="px-3 py-2 text-xs text-gray-400">Searching…</div>}
        {!loading && results.length === 0 && (
          <div className="px-3 py-2 text-xs text-gray-400">
            {segment || q.trim() ? 'No matches.' : 'Pick a segment or search to begin.'}
          </div>
        )}
        {!loading && results.map((m) => (
          <button key={m.staff_code} onClick={() => onChange(m)}
            className="w-full text-left px-3 py-2 hover:bg-gray-50">
            <div className="text-sm text-gray-900">{displayName(m.name, (m as any).display_name)}</div>
            <div className="text-xs text-gray-500">
              {m.staff_code}{m.role ? ` · ${m.role}` : ''}{m.segment ? ` · ${m.segment}` : ''}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
