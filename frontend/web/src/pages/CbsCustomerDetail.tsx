// v10.531 Phase 5 Batch γ2 — CBS customer detail page.
//
// Shows full customer record from CBS plus all their accounts.
// Read-only — CBS is the upstream system of record.

import { useNavigate, useParams } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useCbsCustomer } from '@/hooks/useCbsCustomer';
import { Card } from '@/components/Card';
import { Badge } from '@/components/Badge';
import { Button } from '@/components/Button';
import { Skeleton } from '@/components/Skeleton';
import {
  riskRatingTone,
  kycStatusTone,
  type CbsAccount,
} from '@/types/cbs';


// ── Format helpers ──────────────────────────────────────────────────────

function formatAmount(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n) || n === 0) return '—';
  return `${symbol} ${n.toLocaleString()}`;
}

function formatBalance(v: number | undefined, symbol: string): string {
  const n = Number(v);
  if (!Number.isFinite(n)) return '—';
  return `${symbol} ${n.toLocaleString()}`;
}

function formatDate(s: string | undefined | null): string {
  if (!s) return '—';
  return s.slice(0, 10);
}


function accountStatusTone(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  const s = status.toUpperCase();
  if (s === 'ACTIVE')     return 'success';
  if (s === 'DORMANT')    return 'warning';
  if (s === 'INACTIVE')   return 'warning';
  if (s === 'CLOSED')     return 'neutral';
  if (s === 'BLOCKED')    return 'danger';
  return 'neutral';
}


export function CbsCustomerDetail() {
  const { cif } = useParams<{ cif: string }>();
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { customer, accounts, loading, error } = useCbsCustomer(cif);

  const currencySymbol = branding?.currency_symbol ?? 'KES';


  // Loading
  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
          <div className="max-w-5xl mx-auto px-6 py-5">
            <Skeleton className="h-7 w-72 bg-white/20" />
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-6 space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-48 w-full" />
        </main>
      </div>
    );
  }

  // Error
  if (error || !customer) {
    return (
      <div className="min-h-screen bg-gray-50">
        <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
          <div className="max-w-5xl mx-auto px-6 py-5">
            <h1 className="text-xl font-semibold">Customer not found</h1>
          </div>
        </header>
        <main className="max-w-5xl mx-auto px-6 py-6">
          <Card>
            <Card.Body>
              <div className="text-sm text-red-800 mb-3">
                <div className="font-semibold">Could not load customer</div>
                <div className="text-xs">{error || `No customer with CIF ${cif} in CBS.`}</div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => navigate('/cbs')}>
                ← Back to lookup
              </Button>
            </Card.Body>
          </Card>
        </main>
      </div>
    );
  }


  // ── Computed totals from accounts ──
  const totalDeposit = accounts
    .filter((a) => a.category === 'DEPOSIT' || a.category === 'CASA' || a.category === 'TERM_DEPOSIT')
    .reduce((sum, a) => sum + (a.current_balance || 0), 0);
  const nplAccounts = accounts.filter((a) => a.npl_status && a.npl_status.toUpperCase() !== 'PERFORMING' && a.npl_status !== '');


  return (
    <div className="min-h-screen bg-gray-50">
      <header className="text-white shadow" style={{ background: 'var(--brand-secondary)' }}>
        <div className="max-w-5xl mx-auto px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="text-xs text-white/70 mb-1 font-mono">CIF {customer.cif}</div>
              <h1 className="text-xl font-semibold">{customer.full_name}</h1>
              <div className="text-xs text-white/80 mt-1">
                {customer.segment || customer.customer_type}
                {customer.branch_name && <> · {customer.branch_name}</>}
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <Badge tone={kycStatusTone(customer.kyc_status)} size="md">
                KYC: {customer.kyc_status || 'unknown'}
              </Badge>
              {customer.risk_rating && (
                <Badge tone={riskRatingTone(customer.risk_rating)} size="sm">
                  Risk: {customer.risk_rating}
                </Badge>
              )}
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-6 space-y-4">

        <div className="flex items-center justify-between">
          <Button variant="ghost" size="sm" onClick={() => navigate('/cbs')}>
            ← Back to lookup
          </Button>
          <Badge tone="brand" size="sm">γ2</Badge>
        </div>


        {/* Compliance flags */}
        {(customer.aml_flag || customer.fatf_flag || customer.pep_flag) && (
          <Card stripe="accent">
            <Card.Body>
              <div className="text-sm font-semibold text-gray-900 mb-2">Compliance flags raised</div>
              <div className="flex flex-wrap items-center gap-2">
                {customer.aml_flag && <Badge tone="danger" size="md">AML</Badge>}
                {customer.fatf_flag && <Badge tone="danger" size="md">FATF</Badge>}
                {customer.pep_flag && <Badge tone="warning" size="md">PEP</Badge>}
              </div>
              <p className="text-xs text-gray-600 mt-2">
                Customer has one or more compliance flags. Coordinate with Compliance before opening or processing new accounts.
              </p>
            </Card.Body>
          </Card>
        )}


        {/* Identity */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Identity</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Field label="Full name" value={customer.full_name} />
              <Field label="CIF" value={customer.cif} mono />
              <Field label="Customer type" value={customer.customer_type} />
              <Field label="Segment" value={customer.segment} />
              <Field label="Sub-segment" value={customer.sub_segment} />
              <Field label="Sector" value={customer.sector} />
              <Field label="Phone" value={customer.phone} mono />
              <Field label="Email" value={customer.email} />
              <Field label="Onboarded" value={formatDate(customer.date_onboarded)} />
              <Field label="Preferred currency" value={customer.preferred_currency} />
            </div>
          </Card.Body>
        </Card>


        {/* Ownership */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Branch & ownership</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <Field label="Branch" value={`${customer.branch_name || '—'} (${customer.branch_code || '?'})`} />
              <Field label="Region" value={customer.region} />
              <Field label="County" value={customer.county} />
              <Field label="Relationship Manager code" value={customer.relationship_manager_code} mono />
              <Field
                label="Dormant?"
                value={customer.is_dormant_customer ? 'yes' : 'no'}
              />
            </div>
          </Card.Body>
        </Card>


        {/* Financial summary */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Financial summary</h2>
            <span className="text-xs text-gray-500">
              {customer.total_accounts} account{customer.total_accounts === 1 ? '' : 's'} on file
            </span>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <SummaryCard
                label="Total deposits (CBS)"
                value={formatAmount(customer.total_deposit_balance, currencySymbol)}
              />
              <SummaryCard
                label="Total loans (CBS)"
                value={formatAmount(customer.total_loan_balance, currencySymbol)}
              />
              <SummaryCard
                label="Computed deposit total"
                value={formatAmount(totalDeposit, currencySymbol)}
                hint={`across ${accounts.filter((a) => a.category === 'DEPOSIT' || a.category === 'CASA' || a.category === 'TERM_DEPOSIT').length} accounts`}
              />
            </div>
            {nplAccounts.length > 0 && (
              <div className="mt-3 px-3 py-2 rounded-md bg-red-50 border border-red-200 text-sm text-red-800">
                <strong>{nplAccounts.length}</strong> account{nplAccounts.length === 1 ? '' : 's'} in NPL status.
              </div>
            )}
          </Card.Body>
        </Card>


        {/* Accounts list */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Accounts ({accounts.length})
            </h2>
          </Card.Header>
          <Card.Body className="p-0">
            {accounts.length === 0 ? (
              <div className="px-6 py-4 text-xs text-gray-400 italic">
                No accounts on file in CBS.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr className="text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                      <th className="px-4 py-3">Account #</th>
                      <th className="px-4 py-3">Type</th>
                      <th className="px-4 py-3">Branch</th>
                      <th className="px-4 py-3">Ccy</th>
                      <th className="px-4 py-3 text-right">Balance</th>
                      <th className="px-4 py-3 text-right">Loan out.</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3">NPL</th>
                      <th className="px-4 py-3">Opened</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {accounts.map((a) => (
                      <AccountRow key={a.account_number} account={a} symbol={currencySymbol} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card.Body>
        </Card>

      </main>
    </div>
  );
}


// ── Helpers ─────────────────────────────────────────────────────────────

interface FieldProps {
  label:  string;
  value?: string | number | null;
  mono?:  boolean;
}

function Field({ label, value, mono }: FieldProps) {
  const display = value === null || value === undefined || value === '' ? '—' : String(value);
  return (
    <div>
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className={`text-sm text-gray-900 mt-0.5 ${mono ? 'font-mono' : ''}`}>{display}</div>
    </div>
  );
}


interface SummaryCardProps {
  label: string;
  value: string;
  hint?: string;
}

function SummaryCard({ label, value, hint }: SummaryCardProps) {
  return (
    <div className="px-3 py-2 rounded-md border border-gray-200 bg-gray-50">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div className="text-base font-semibold text-gray-900 mt-0.5 font-mono">{value}</div>
      {hint && <div className="text-xs text-gray-500 mt-0.5">{hint}</div>}
    </div>
  );
}


function AccountRow({ account, symbol }: { account: CbsAccount; symbol: string }) {
  return (
    <tr className="hover:bg-gray-50 transition">
      <td className="px-4 py-2 font-mono text-xs text-gray-700">{account.account_number}</td>
      <td className="px-4 py-2 text-gray-700">{account.account_type_name || account.category || '—'}</td>
      <td className="px-4 py-2 text-xs text-gray-600">{account.branch_name || '—'}</td>
      <td className="px-4 py-2 text-xs">{account.currency}</td>
      <td className="px-4 py-2 text-right font-mono text-xs">{formatBalance(account.current_balance, symbol)}</td>
      <td className="px-4 py-2 text-right font-mono text-xs">{formatBalance(account.loan_outstanding, symbol)}</td>
      <td className="px-4 py-2">
        <Badge tone={accountStatusTone(account.account_status)} size="sm">
          {account.account_status || '—'}
        </Badge>
      </td>
      <td className="px-4 py-2 text-xs">
        {account.npl_status && account.npl_status.toUpperCase() !== 'PERFORMING' ? (
          <Badge tone="danger" size="sm">{account.npl_status}</Badge>
        ) : (
          <span className="text-gray-400">—</span>
        )}
      </td>
      <td className="px-4 py-2 text-xs text-gray-600">{formatDate(account.date_opened)}</td>
    </tr>
  );
}
