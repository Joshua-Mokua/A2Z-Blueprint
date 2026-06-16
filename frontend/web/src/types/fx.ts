// P4-1c — TypeScript types for the operational FX domain.
//
// Mirrors utils/fx_engine.py (FxRateStore) and the FX admin endpoints in
// utils/api.py (/api/fx/rates, /api/fx/resolve). KES is base (rate_to_kes = 1).

export type CurrencyBook = 'LCY' | 'FCY';
export type FxRateType = 'mid' | 'buy' | 'sell';

export interface FxRate {
  currency:        string;       // ISO code, e.g. "USD"
  rate_to_kes:     number;       // 1 unit of currency -> KES
  rate_type:       FxRateType;
  effective_date:  string;       // YYYY-MM-DD
  source?:         string;       // "admin" | "system"
  entered_by?:     string;
  active?:         boolean;
  recorded_at?:    string;
}

export interface FxRatesResponse {
  base_currency:   string;       // "KES"
  rates:           FxRate[];
}

export interface FxResolveResponse {
  currency:        string;
  rate_to_kes:     number;
  rate_type:       FxRateType;
  as_of?:          string | null;
}

export interface FxRateUpsertRequest {
  currency:        string;
  rate_to_kes:     number;
  effective_date:  string;
  rate_type:       FxRateType;
}

export interface FxRateUpsertResponse {
  rate:            FxRate;
  status:          string;
}

// The normalized money set stamped on bookings (P4-1b). Optional everywhere —
// legacy records pre-date the stamp; unconfigured currencies leave fx_* null.
export interface NormalizedMoney {
  currency?:        string;
  currency_book?:   CurrencyBook;
  fx_rate?:         number | null;
  amount_kes?:      number | null;
  fx_rate_date?:    string | null;
  fx_rate_source?:  string | null;
}
