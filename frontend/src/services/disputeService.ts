import { api } from "./api";
import { mapDispute, type ApiDispute } from "./mappers";
import type {
  Dispute,
  DisputeCategory,
  DisputeDecision,
  DisputeEvidence,
  DisputeStatus,
} from "../types";

// ============================================================
// DISPUTE SERVICE — Phase 12 dispute resolution
// (participant endpoints + admin queue; access enforced server-side)
// ============================================================

export interface CreateDisputePayload {
  booking: number;
  category: DisputeCategory;
  description?: string;
}

export interface AddEvidencePayload {
  kind: "text" | "photo" | "document";
  content?: string;
}

export interface ActOnDisputePayload {
  action: "transition" | "resolve" | "reject";
  status?: DisputeStatus;
  decision?: DisputeDecision;
  decisionAmount?: number | null;
  resolution?: string;
}

export const disputeService = {
  /** GET /disputes/ — the caller's disputes (participant or admin). */
  async getDisputes(): Promise<Dispute[]> {
    const { data } = await api.get<ApiDispute[]>("/disputes/");
    return data.map(mapDispute);
  },

  /** GET /disputes/:id/ — detail with evidence (participant or admin). */
  async getDispute(id: number): Promise<Dispute> {
    const { data } = await api.get<ApiDispute>(`/disputes/${id}/`);
    return mapDispute(data);
  },

  /** POST /disputes/ — open a dispute on an approved booking. */
  async createDispute(payload: CreateDisputePayload): Promise<Dispute> {
    const { data } = await api.post<ApiDispute>("/disputes/", payload);
    return mapDispute(data);
  },

  /** POST /disputes/:id/evidence/ — add a text statement (participant/admin). */
  async addEvidence(id: number, payload: AddEvidencePayload): Promise<DisputeEvidence> {
    const { data } = await api.post(`/disputes/${id}/evidence/`, payload);
    return {
      id: data.id,
      dispute: data.dispute,
      uploadedBy: data.uploaded_by,
      uploadedByUsername: data.uploaded_by_username,
      kind: data.kind,
      kindDisplay: data.kind_display,
      content: data.content,
      file: data.file,
      createdAt: data.created_at,
    };
  },

  /** GET /disputes/admin/ — every dispute (admin only). */
  async getAdminDisputes(status = "open"): Promise<Dispute[]> {
    const { data } = await api.get<ApiDispute[]>("/disputes/admin/", {
      params: status && status !== "all" ? { status } : undefined,
    });
    return data.map(mapDispute);
  },

  /** POST /disputes/admin/:id/action/ — transition | resolve | reject (admin). */
  async actOnDispute(id: number, payload: ActOnDisputePayload): Promise<Dispute> {
    const { data } = await api.post<ApiDispute>(`/disputes/admin/${id}/action/`, payload);
    return mapDispute(data);
  },
};

export default disputeService;
