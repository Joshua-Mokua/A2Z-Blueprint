// v10.531 Phase 5 Batch γ2 — Standalone CBS customer viewer.
//
// Search bar that uses CustomerSearchInput; picking a customer
// navigates to /cbs/{cif} for the detail view.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { CustomerSearchInput } from '@/components/CustomerSearchInput';
import { Card } from '@/components/Card';
import { Button } from '@/components/Button';
import { PageHeader } from '@/components/PageHeader';


export function Cbs() {
  const navigate = useNavigate();
  const [searchValue, setSearchValue] = useState<string>('');
  const [directCif, setDirectCif] = useState<string>('');


  const onDirectCifLookup = () => {
    const cif = directCif.trim();
    if (cif) {
      navigate(`/cbs/${encodeURIComponent(cif)}`);
    }
  };


  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="Customer Lookup"
        breadcrumbs={[{ label: 'Reference & Admin' }, { label: 'Customer Lookup' }]}
        subtitle="Search the core banking system by name or CIF."
      />

      <main className="max-w-5xl mx-auto px-6 py-6 space-y-4">

        {/* Name search */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Search by name</h2>
          </Card.Header>
          <Card.Body>
            <CustomerSearchInput
              value={searchValue}
              onChange={setSearchValue}
              onCustomerPicked={(c) => navigate(`/cbs/${encodeURIComponent(c.cif)}`)}
              placeholder="Type at least 3 characters of the customer's name…"
            />
            <p className="mt-2 text-xs text-gray-500">
              Picking a customer from the dropdown navigates to their detail page.
              You can also press <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-xs">↓</kbd>
              <kbd className="px-1.5 py-0.5 bg-gray-100 border border-gray-200 rounded text-xs ml-0.5">Enter</kbd> to pick the first match.
            </p>
          </Card.Body>
        </Card>


        {/* Direct CIF lookup */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Lookup by CIF</h2>
          </Card.Header>
          <Card.Body>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={directCif}
                onChange={(e) => setDirectCif(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onDirectCifLookup();
                }}
                placeholder="e.g. 100000001"
                className="flex-1 h-10 px-3 rounded-md border border-gray-300 bg-white text-sm font-mono focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
              />
              <Button variant="primary" onClick={onDirectCifLookup} disabled={!directCif.trim()}>
                Open
              </Button>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              CIF range in the simulation: 100000001 – 100700000.
            </p>
          </Card.Body>
        </Card>


        {/* Helper card */}
        <Card>
          <Card.Body>
            <div className="text-xs text-gray-500 italic">
              <strong>About CBS lookup.</strong> This page mirrors the customer database (CBS)
              that the bank uses for KYC and account management. Searches are bank-wide
              (any RM can find any customer). Exact-CIF lookups are audited; name searches are not.
            </div>
          </Card.Body>
        </Card>

      </main>
    </div>
  );
}
