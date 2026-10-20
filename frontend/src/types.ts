export type ChartPoint = { date: string; balance_cents: number };
export type Envelope = {
  id: number;
  name: string;
  code: string | null;
  description: string;
  icon: string;
  status: "ACTIVE" | "ARCHIVED";
  is_system: boolean;
  sort_order: number;
  balance_cents: number;
  month_net_cents?: number;
  month_movement_count?: number;
  month_message?: string | null;
  last_movement_date?: string | null;
  chart?: ChartPoint[];
};
export type Reconciliation = {
  bank_balance_cents: number;
  envelopes_total_cents: number;
  unassigned_cents: number;
  difference_cents: number;
  reconciled: boolean;
  last_sync_at: string | null;
  last_sync_error: string | null;
};
export type Anomalies = {
  count: number;
  unassigned_transaction_ids: number[];
  negative_envelope_ids: number[];
  suspected_duplicate_fingerprints: string[];
  reconciliation: Reconciliation;
};
export type Dashboard = {
  reconciliation: Reconciliation;
  envelopes: Envelope[];
  anomalies: Anomalies;
};
export type Movement = {
  id: number;
  envelope_id: number;
  envelope_name: string;
  transaction_id: number | null;
  event_id: string;
  effective_date: string;
  amount_cents: number;
  kind: "INITIAL" | "BANK" | "REALLOCATION" | "CORRECTION";
  reason: string;
};
export type Transaction = {
  id: number;
  booking_date: string;
  amount_cents: number;
  raw_label: string;
};
export type AllocatedTransaction = Transaction & {
  envelope_name: string;
  allocation: { envelope_id: number };
};
export type Account = { id: number; name: string; activation_date: string };
export type Session = { actor: string; csrf_token: string };
export type Summary = Envelope & {
  year: number;
  in_cents: number;
  out_cents: number;
};
