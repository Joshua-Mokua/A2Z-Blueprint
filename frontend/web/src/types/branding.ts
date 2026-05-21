// v10.495 — TypeScript types for the /api/branding response.
//
// This is the contract between the FastAPI backend
// (utils/api_branding.py) and the React frontend. Backend Python
// returns a dict matching this shape. If you change one side,
// change both.
//
// Audit gate G381 enforces that this type matches utils/api_branding.py's
// response shape.

export interface BrandColors {
  primary: string;
  secondary: string;
  accent: string;
}

export interface Branding {
  bank_name: string;
  app_name: string;
  currency: string;
  currency_symbol: string;
  country: string;
  regulator: string;
  regulator_full: string;
  core_banking_system: string;
  tax_authority: string;
  brand: BrandColors;
  ip_notice: string;
}
