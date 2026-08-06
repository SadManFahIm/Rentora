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

function mapSignal(api: ApiSignal): FraudReport["signals"][number] {
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

function mapReport(api: ApiReport): FraudReport {
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
  async getReports(params: { status?: string; severity?: string } = {}): Promise<FraudReport[]> {
    const { data } = await api.get<ApiReport[]>("/fraud/reports/", { params });
    return data.map(mapReport);
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

export default fraudService;
