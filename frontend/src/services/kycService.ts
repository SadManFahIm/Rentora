import { api } from "./api";
import type { KycApplication, KycAuditEntry, KycDocType, KycDocument, KycSla } from "../types";

// ============================================================
// KYC SERVICE — document upload + admin review panel
// ============================================================

interface ApiKycDocument {
  id: number;
  doc_type: KycDocType;
  doc_type_display: string;
  file: string;
  status: KycDocument["status"];
  status_display: string;
  review_note: string;
  created_at: string;
  reviewed_at: string | null;
}

interface ApiKycAuditEntry {
  id: number;
  action: KycAuditEntry["action"];
  actor_username: string;
  actor_name: string;
  user_id: number | null;
  user_name: string;
  note: string;
  created_at: string;
}

interface ApiKycApplication {
  id: number;
  username: string;
  email: string;
  name: string;
  phone: string;
  role: string;
  nid_verified: boolean;
  documents: ApiKycDocument[];
}

const mapDocument = (d: ApiKycDocument): KycDocument => ({
  id: d.id,
  docType: d.doc_type,
  docTypeDisplay: d.doc_type_display,
  fileUrl: d.file,
  status: d.status,
  statusDisplay: d.status_display,
  reviewNote: d.review_note,
  createdAt: d.created_at,
  reviewedAt: d.reviewed_at,
});

const mapApplication = (a: ApiKycApplication): KycApplication => ({
  id: a.id,
  username: a.username,
  email: a.email,
  name: a.name,
  phone: a.phone,
  role: a.role,
  nidVerified: a.nid_verified,
  documents: a.documents.map(mapDocument),
});

export const kycService = {
  /** GET /users/kyc/documents/ — the caller's own submitted documents. */
  async myDocuments(): Promise<KycDocument[]> {
    const { data } = await api.get<ApiKycDocument[]>("/users/kyc/documents/");
    return data.map(mapDocument);
  },

  /**
   * POST /users/kyc/documents/ — upload a KYC proof (multipart).
   * The shared instance defaults to `Content-Type: application/json`, which
   * must be explicitly cleared for FormData: axios merges per-request headers
   * over the instance defaults, so `undefined` removes it and the browser
   * sets `multipart/form-data` with the boundary itself.
   */
  async uploadDocument(docType: KycDocType, file: File): Promise<KycDocument> {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    const { data } = await api.post<ApiKycDocument>("/users/kyc/documents/", form, {
      headers: { "Content-Type": undefined },
    });
    return mapDocument(data);
  },

  /**
   * GET a document's bytes with auth, as a blob — the admin panel fetches
   * this (instead of <a href>) so the private file never hits the browser
   * without a token.
   */
  async fetchDocumentFile(fileUrl: string): Promise<Blob> {
    const { data } = await api.get<Blob>(fileUrl, { responseType: "blob" });
    return data;
  },

  /** GET /users/kyc/pending/ — admin review queue (403 for non-admins). */
  async pendingApplications(): Promise<KycApplication[]> {
    const { data } = await api.get<ApiKycApplication[]>("/users/kyc/pending/");
    return data.map(mapApplication);
  },

  /** POST /users/kyc/{userId}/review/ — admin approve (or reject/revoke). */
  async reviewApplication(userId: number, approved: boolean, note = ""): Promise<KycApplication> {
    const { data } = await api.post<ApiKycApplication>(`/users/kyc/${userId}/review/`, {
      approved,
      note,
    });
    return mapApplication(data);
  },

  /** GET /users/kyc/sla/ — admin-only review-queue health stats (403 otherwise). */
  async slaStats(): Promise<KycSla> {
    const { data } = await api.get<{
      pending_count: number;
      resolved_count: number;
      avg_review_hours: number | null;
      last_7d_decisions: number;
      last_7d_avg_review_hours: number | null;
      prev_7d_decisions: number;
      decision_delta_7d: number;
      pending_oldest_hours: number | null;
      breaches: string[];
      trend_30d: { date: string; decisions: number; avg_review_hours: number | null }[];
    }>("/users/kyc/sla/");
    return {
      pendingCount: data.pending_count,
      resolvedCount: data.resolved_count,
      avgReviewHours: data.avg_review_hours,
      last7dDecisions: data.last_7d_decisions,
      last7dAvgReviewHours: data.last_7d_avg_review_hours,
      prev7dDecisions: data.prev_7d_decisions,
      decisionDelta7d: data.decision_delta_7d,
      pendingOldestHours: data.pending_oldest_hours,
      breaches: data.breaches,
      trend30d: data.trend_30d.map((d) => ({
        date: d.date,
        decisions: d.decisions,
        avgReviewHours: d.avg_review_hours,
      })),
    };
  },

  /** GET /users/kyc/audit/ — admin-only approve/reject history (newest first). */
  async auditTrail(): Promise<KycAuditEntry[]> {
    const { data } = await api.get<ApiKycAuditEntry[]>("/users/kyc/audit/");
    return data.map((e) => ({
      id: e.id,
      action: e.action,
      actorUsername: e.actor_username,
      actorName: e.actor_name,
      userId: e.user_id,
      userName: e.user_name,
      note: e.note,
      createdAt: e.created_at,
    }));
  },
};

export default kycService;
