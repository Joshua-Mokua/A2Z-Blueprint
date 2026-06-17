// v10.531 Phase 5 Batch γ2 — CustomerSearchInput reusable component.
//
// Drop-in replacement for a plain client-name <Input>. Wraps an input
// with a debounced search dropdown of CBS customer matches. User can:
//   - Type freely (debounced 300ms search kicks in at 3+ chars)
//   - Click a result OR ArrowDown/Up + Enter to pick
//   - Esc to close the dropdown without picking
//
// Picking a customer fires `onCustomerPicked` with the full CbsCustomer
// object. The parent component decides what to do (typically: set
// clientName state + clientType derivation + maybe other fields).
//
// The component remains controlled — value is owned by the parent.
// `onChange` fires on every keystroke so the parent's clientName state
// stays in sync with the textbox even when the user is typing without
// picking from the dropdown (free-text fallback).

import { useState, useRef, useEffect } from 'react';
import type { ReactNode } from 'react';
import { useCustomerSearch } from '@/hooks/useCustomerSearch';
import { Badge } from '@/components/Badge';
import { Skeleton } from '@/components/Skeleton';
import type { CbsCustomer } from '@/types/cbs';


export interface CustomerSearchInputProps {
  /** Current text value (parent-controlled). */
  value:               string;
  /** Fired on every keystroke; parent must update its own state. */
  onChange:            (newValue: string) => void;
  /** Fired when user picks a customer from the dropdown. */
  onCustomerPicked?:   (customer: CbsCustomer) => void;
  /** Optional: fired when textbox is cleared or text diverges from picked customer. */
  onCustomerCleared?:  () => void;

  /** Display props */
  label?:              ReactNode;
  placeholder?:        string;
  disabled?:           boolean;
  error?:              string;

  /** The last-picked customer, if any. Shown as a badge under the input. */
  pickedCustomer?:     CbsCustomer | null;
}


export function CustomerSearchInput({
  value,
  onChange,
  onCustomerPicked,
  onCustomerCleared,
  label,
  placeholder = 'Type a name (min 3 chars) to search CBS…',
  disabled = false,
  error,
  pickedCustomer,
}: CustomerSearchInputProps) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const containerRef = useRef<HTMLDivElement>(null);

  const { results, loading, active } = useCustomerSearch(value, 300, 10);

  // Click-outside closes the dropdown.
  useEffect(() => {
    const onDocumentClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocumentClick);
    return () => document.removeEventListener('mousedown', onDocumentClick);
  }, []);

  // Reset highlighted index when results change (so it doesn't point past end).
  useEffect(() => {
    setHighlightedIndex(results.length > 0 ? 0 : -1);
  }, [results]);

  // Determine whether the textbox now diverges from the picked customer's
  // name — if so, the picked badge is stale and should be cleared.
  useEffect(() => {
    if (pickedCustomer && value !== pickedCustomer.full_name) {
      onCustomerCleared?.();
    }
    // Only depend on value/pickedCustomer; onCustomerCleared can re-mount
    // each render but we don't want to re-fire on that.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, pickedCustomer]);

  const handlePick = (customer: CbsCustomer) => {
    onChange(customer.full_name);
    onCustomerPicked?.(customer);
    setDropdownOpen(false);
    setHighlightedIndex(-1);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!dropdownOpen || results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightedIndex((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      if (highlightedIndex >= 0 && highlightedIndex < results.length) {
        e.preventDefault();
        handlePick(results[highlightedIndex]);
      }
    } else if (e.key === 'Escape') {
      setDropdownOpen(false);
      setHighlightedIndex(-1);
    }
  };


  return (
    <div ref={containerRef} className="relative">
      {label && (
        <label className="text-sm font-medium text-gray-700 mb-1 block">
          {label}
        </label>
      )}
      <input
        type="text"
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setDropdownOpen(true);
        }}
        onFocus={() => setDropdownOpen(true)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        className={`w-full h-10 px-3 rounded-md border bg-white text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/20 ${
          error ? 'border-red-400 focus:border-red-500' : 'border-gray-300 focus:border-brand-primary'
        }`}
      />
      {error && (
        <div className="mt-1 text-xs text-red-700">{error}</div>
      )}

      {/* Picked-customer confirmation badge (below input, persists until cleared) */}
      {pickedCustomer && value === pickedCustomer.full_name && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs">
          <Badge tone="success" size="sm">✓ matched in CBS</Badge>
          <span className="font-mono text-gray-700">CIF {pickedCustomer.cif}</span>
          <span className="text-gray-400">·</span>
          <span className="text-gray-700">{pickedCustomer.segment || pickedCustomer.customer_type}</span>
          {pickedCustomer.branch_name && (
            <>
              <span className="text-gray-400">·</span>
              <span className="text-gray-700">{pickedCustomer.branch_name}</span>
            </>
          )}
          {pickedCustomer.relationship_manager_code && (
            <>
              <span className="text-gray-400">·</span>
              <span className="text-gray-600">RM {pickedCustomer.relationship_manager_code}</span>
            </>
          )}
        </div>
      )}

      {/* Dropdown */}
      {dropdownOpen && active && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg max-h-80 overflow-auto">
          {loading && (
            <div className="px-3 py-2 space-y-1">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-5 w-2/3" />
              <Skeleton className="h-5 w-3/5" />
            </div>
          )}

          {!loading && results.length === 0 && (
            <div className="px-3 py-3 text-xs text-gray-500 italic">
              No customers match "{value}". You can still proceed with free-text entry.
            </div>
          )}

          {!loading && results.length > 0 && (
            <ul className="divide-y divide-gray-100">
              {results.map((c, i) => (
                <li
                  key={c.cif}
                  onMouseDown={(e) => {
                    // mousedown not click — click fires after blur which
                    // would close the dropdown before our handler runs.
                    e.preventDefault();
                    handlePick(c);
                  }}
                  onMouseEnter={() => setHighlightedIndex(i)}
                  className={`px-3 py-2 cursor-pointer transition ${
                    i === highlightedIndex ? 'bg-brand-primary/10' : 'hover:bg-gray-50'
                  }`}
                >
                  <div className="text-sm font-medium text-gray-900">
                    {c.full_name}
                  </div>
                  <div className="text-xs text-gray-600 mt-0.5 flex flex-wrap items-center gap-1.5">
                    <span className="font-mono">CIF {c.cif}</span>
                    <span className="text-gray-400">·</span>
                    <span>{c.segment || c.customer_type}</span>
                    {c.branch_name && (
                      <>
                        <span className="text-gray-400">·</span>
                        <span>{c.branch_name}</span>
                      </>
                    )}
                    {c.relationship_manager_code && (
                      <>
                        <span className="text-gray-400">·</span>
                        <span className="text-gray-500">RM {c.relationship_manager_code}</span>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
