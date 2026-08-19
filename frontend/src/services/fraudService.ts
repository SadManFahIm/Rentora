import { api } from "./api";
import { mapRoom, type ApiRoom } from "./mappers";
import type { FraudReport, FraudStatus } from "../types";

// ============================================================
// FRAUD SERVICE — /fraud/ endpoints
// ============================================================

interface ApiSignal {
  id: number;
  detector: string;
  detector_display: string;
  severity: string;
  message: string;
  detail: Record<string, unknown>;
  created_at: string;
}

interface ApiReport {
  id: number;
  room: ApiRoom;
  severity: string;
  severity_display: string;
  status: string;
  status_display: string;
  score: number;
  summary: string;
  signals: ApiSignal[];
  created_at: string;
  updated_at: string;
}

interface ApiStatus {
  room_id: number;
  severity: string;
  score: number;
  flagged: boolean;
  message: string;
}

export function mapSignal(api: ApiSignal): FraudReport["signals"][number] {
  return {
    id: api.id,
    detector: api.detector,
    detectorDisplay: api.detector_display,
    severity: api.severity as FraudReport["signals"][number]["severity"],
    message: api.message,
    detail: api.detail,
    createdAt: api.created_at,
  };
}

export function mapReport(api: ApiReport): FraudReport {
  return {
    id: api.id,
    room: mapRoom(api.room),
    severity: api.severity as FraudReport["severity"],
    severityDisplay: api.severity_display,
    status: api.status as FraudReport["status"],
    statusDisplay: api.status_display,
    score: api.score,
    summary: api.summary,
    signals: api.signals.map(mapSignal),
    createdAt: api.created_at,
    updatedAt: api.updated_at,
  };
}

export const fraudService = {
  /** GET /fraud/rooms/{roomId}/status/ — public badge data. */
  async getRoomStatus(roomId: number): Promise<FraudStatus> {
    const { data } = await api.get<ApiStatus>(`/fraud/rooms/${roomId}/status/`);
    return {
      roomId: data.room_id,
      severity: data.severity as FraudStatus["severity"],
      score: data.score,
      flagged: data.flagged,
      message: data.message,
    };
  },

  /** GET /fraud/reports/ — my rooms' reports (admin: all). */
  async getReports(
    params: {
      status?: string;
      severity?: string;
      area?: string;
      detector?: string;
      q?: string;
      ordering?: string;
    } = {}
  ): Promise<FraudReport[]> {
    const { data } = await api.get<ApiReport[]>("/fraud/reports/", { params });
    return data.map(mapReport);
  },

  /** GET /fraud/summary/ — admin-only aggregate stats. */
  async getSummary(): Promise<FraudSummary> {
    const { data } = await api.get<FraudSummary>("/fraud/summary/");
    return data;
  },

  /** GET /fraud/audit/ — admin-only append-only fraud audit trail. */
  async getAuditLog(): Promise<FraudAuditEntry[]> {
    const { data } = await api.get<FraudAuditEntry[]>("/fraud/audit/");
    return data;
  },

  /** GET /fraud/rings/ — admin-only coordinated-account rings, computed
   * live from shared phones / shared IPs + same-area listings. A ring is a
   * review queue, never an automatic block. */
  async getRings(): Promise<FraudRingsOverview> {
    const { data } = await api.get<FraudRingsOverview>("/fraud/rings/");
    return data;
  },

  /** POST /fraud/rooms/{roomId}/scan/ — re-run the detector (owner/admin). */
  async scanRoom(roomId: number): Promise<FraudReport> {
    const { data } = await api.post<ApiReport>(`/fraud/rooms/${roomId}/scan/`);
    return mapReport(data);
  },

  /** POST /fraud/reports/{reportId}/review/ — admin: reviewed or dismissed. */
  async reviewReport(reportId: number, action: "reviewed" | "dismissed"): Promise<FraudReport> {
    const { data } = await api.post<ApiReport>(`/fraud/reports/${reportId}/review/`, { action });
    return mapReport(data);
  },
};

export interface FraudSummary {
  total: number;
  flagged: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  open: number;
  reviewed: number;
  dismissed: number;
  clean: number;
  by_detector: Record<string, number>;
}

export interface FraudAuditEntry {
  id: number;
  action: string;
  actor: string | null;
  room_id: number | null;
  target_id: string;
  created_at: string;
}

// ---- Phase 15 — D8 coordinated-account rings (admin desk view) ----

export interface FraudRingMember {
  user_id: number;
  username: string;
  email: string;
  role: string;
  nid_verified: boolean;
  tenant_verified: boolean;
  phone: string;
  connected_to: number[];
  listings_count: number;
}

export interface FraudRingEdge {
  users: [number, number];
  strength: "strong" | "weak";
  evidence: string;
}

export interface FraudRingFlaggedRoom {
  room_id: number;
  title: string;
  area: string;
  owner_id: number;
  severity: string;
  score: number;
}

export interface FraudRing {
  ring_id: number;
  member_count: number;
  score: number;
  strong_edges: number;
  weak_edges: number;
  member_scores: Record<string, number>;
  members: FraudRingMember[];
  edges: FraudRingEdge[];
  flagged_rooms: FraudRingFlaggedRoom[];
}

export interface FraudRingsOverview {
  rings: FraudRing[];
  ring_count: number;
  user_count: number;
  as_of: string;
  note: string;
}

export default fraudService;
