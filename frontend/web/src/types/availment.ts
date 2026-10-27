// Module C — CAD Availment Memo API contract.

export type AvailmentStatus =
  | 'not_started'
  | 'draft'
  | 'ready_for_approval'
  | 'approved'
  | 'sent_to_trops'
  | 'disbursed';

export type AvailmentInstructionType =
  | 'insurance_collection'
  | 'prior_loan_liquidation'
  | 'external_bank_payoff'
  | 'residual_lien_hold'
  | 'other';

export interface AvailmentInstruction {
  type: AvailmentInstructionType;
  [key: string]: unknown;
}

export interface AvailmentMemoData {
  fields?: Record<string, unknown>;
  instructions?: AvailmentInstruction[];
  approval_returns?: Array<Record<string, unknown>>;
}

export interface AvailmentMemo {
  id: string;
  credit_admin_case_id: string;
  application_id: string;
  status: Exclude<AvailmentStatus, 'not_started'>;
  current_version: number;
  data: AvailmentMemoData;
  approval_assignee_code?: string | null;
  approval_assignee_name?: string | null;
  approval_assignee_role?: string | null;
  approval_requested_by?: string | null;
  approval_requested_by_code?: string | null;
  approval_requested_at?: string | null;
  approval_note?: string | null;
  approved_by?: string | null;
  approved_at?: string | null;
  created_by?: string | null;
  updated_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface AvailmentSource {
  credit_admin_case_id?: string;
  application_id?: string;
  client_name?: string;
  product?: string;
  amount?: number | string | null;
  currency?: string;
  approval_date?: string | null;
  conditions?: unknown[];
  facility_security_type?: string | null;
  security_subtype?: string | null;
  post_approval_verification?: Record<string, unknown>;
  document_files?: Record<string, unknown>;
  decision?: Record<string, unknown>;
}

export interface AvailmentResponse {
  credit_admin_case_id: string;
  application_id: string;
  status: AvailmentStatus;
  memo: AvailmentMemo | null;
  source: AvailmentSource;
}

export interface AvailmentDraftRequest {
  fields: Record<string, unknown>;
  instructions: AvailmentInstruction[];
}

export interface AvailmentApprovalRequest {
  approver_code: string;
  note?: string;
}

export interface AvailmentReturnRequest {
  reason: string;
}
