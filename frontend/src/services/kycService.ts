import { api } from "./api";
import type { KycApplication, KycDocType, KycDocument } from "../types";

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
   * No manual Content-Type header: axios v1 strips it for FormData in the
   * browser so the browser adds the boundary itself — a hand-set header
   * would arrive without a boundary and the server would reject it.
   */
  async uploadDocument(docType: KycDocType, file: File): Promise<KycDocument> {
    const form = new FormData();
    form.append("doc_type", docType);
    form.append("file", file);
    const { data } = await api.post<ApiKycDocument>("/users/kyc/documents/", form);
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
};

export default kycService;
