import { api } from "./api";

// ============================================================
// AI LISTING AUTOPILOT (Phase 19.3) — landlord weekly recommendations
// ============================================================

export type AutopilotProposalType =
  | "TITLE_UPDATE"
  | "DESCRIPTION_UPDATE"
  | "AMENITY_UPDATE"
  | "PHOTO_RECOMMENDATION"
  | "PRICE_UPDATE"
  | "LISTING_RENEWAL";

export type AutopilotProposalStatus =
  "pending" | "approved" | "applied" | "rejected" | "expired" | "failed";

/** A typed, landlord-reviewable recommendation produced by the weekly run. */
export interface AutopilotProposal {
  key: string;
  type: AutopilotProposalType;
  status: AutopilotProposalStatus;
  title: string;
  summary: string;
  room_id: number | null;
  grounding_key: string;
  recommendation: Record<string, unknown>;
  arguments: Record<string, unknown>;
  created_at: string | null;
  expires_at: string | null;
  reviewed_at: string | null;
  applied_at: string | null;
  application_result: Record<string, unknown> | null;
  rejection_reason: string | null;
  conversation_id: number | null;
}

/** One listing's weekly analysis snapshot (scores + grounding). */
export interface AutopilotAnalysis {
  id: number;
  room_id: number;
  week_key: string;
  eligible: boolean;
  quality_score: number | null;
  property_score: number | null;
  property_confidence: string;
  price_direction: string;
  suggested_price: number | null;
  stale_days: number;
  summary: string;
  created_at: string | null;
}

export interface AutopilotOverview {
  enabled: boolean;
  pending_count: number;
  agent: string;
}

export interface AutopilotConsentResult {
  proposal_key: string;
  status: string;
}

export interface AutopilotBulkResult {
  applied: { key: string; status: string }[];
  skipped: { key: string; reason: string }[];
}

/** Feature availability + pending count for the dashboard header. */
export const getAutopilotOverview = (): Promise<AutopilotOverview> =>
  api.get<AutopilotOverview>("/autopilot/overview/").then((r) => r.data);

/** The landlord's own proposals, optionally filtered by status. */
export const listAutopilotProposals = (
  status?: AutopilotProposalStatus | ""
): Promise<{ proposals: AutopilotProposal[] }> =>
  api
    .get<{ proposals: AutopilotProposal[] }>("/autopilot/proposals/", {
      params: status ? { status } : undefined,
    })
    .then((r) => r.data);

/** The landlord's weekly analysis snapshots. */
export const listAutopilotAnalyses = (): Promise<{ analyses: AutopilotAnalysis[] }> =>
  api.get<{ analyses: AutopilotAnalysis[] }>("/autopilot/analyses/").then((r) => r.data);

/** Approve + apply a pending autopilot proposal (landlord self-consent). */
export const approveAutopilotProposal = (proposalKey: string): Promise<AutopilotConsentResult> =>
  api
    .post<AutopilotConsentResult>(`/autopilot/proposals/${proposalKey}/approve/`)
    .then((r) => r.data);

/** Reject a pending autopilot proposal (landlord self-reject). */
export const rejectAutopilotProposal = (
  proposalKey: string,
  reason?: string
): Promise<AutopilotConsentResult> =>
  api
    .post<AutopilotConsentResult>(`/autopilot/proposals/${proposalKey}/reject/`, {
      reason: reason ?? "",
    })
    .then((r) => r.data);

/** Approve+apply every valid selected proposal in one batch. */
export const bulkApproveAutopilotProposals = (
  proposalKeys: string[]
): Promise<AutopilotBulkResult> =>
  api
    .post<AutopilotBulkResult>("/autopilot/proposals/bulk-approve/", {
      proposal_keys: proposalKeys,
    })
    .then((r) => r.data);
