import { api } from "./api";
import { mapRoom, type ApiRoom } from "./mappers";
import type { Room } from "../types";

// ============================================================
// VISION SERVICE — Phase 14 AI v3 (photo intelligence)
// ============================================================

export interface VisionObservation {
  kind: string;
  label: string;
  confidence: number;
}

export interface VisionColour {
  hex: string;
  name: string;
  share: number;
}

export interface VisionAnalysis {
  available: boolean;
  reason?: string;
  provider: string;
  caption: string;
  observations: VisionObservation[];
  suggested_amenities: string[];
  palette: VisionColour[];
  photo_count: number;
  note: string;
}

export interface VisionDraft {
  title: string;
  description: string;
  amenities: string[];
  observations: VisionObservation[];
  note: string;
}

export interface VisionMatch extends Room {
  match_score: number;
  reasons: string[];
}

interface ApiVisionMatch extends ApiRoom {
  match_score: number;
  reasons: string[];
}

export interface VisionSearchResult {
  matches: VisionMatch[];
  note: string;
}

/** POST /rooms/:id/vision/analyze/ — run (and store) photo intelligence. */
async function analyzeRoom(roomId: number): Promise<VisionAnalysis> {
  const { data } = await api.post<VisionAnalysis>(`/rooms/${roomId}/vision/analyze/`);
  return data;
}

/** GET /rooms/:id/vision/ — the stored analysis (404 before first run). */
async function getVision(roomId: number): Promise<VisionAnalysis> {
  const { data } = await api.get<VisionAnalysis>(`/rooms/${roomId}/vision/`);
  return data;
}

/** POST /rooms/:id/vision/description/ — draft from the listing's photos. */
async function getVisionDescription(roomId: number): Promise<VisionDraft> {
  const { data } = await api.post<VisionDraft>(`/rooms/${roomId}/vision/description/`);
  return data;
}

/** POST /rooms/vision/search/ — upload a photo, get look-alike rooms. */
async function searchByImage(file: File): Promise<VisionSearchResult> {
  const form = new FormData();
  form.append("image", file);
  const { data } = await api.post<{
    matches: ApiVisionMatch[];
    note: string;
  }>("/rooms/vision/search/", form, {
    headers: { "Content-Type": undefined },
  });
  return {
    matches: data.matches.map((m) => ({
      ...mapRoom(m),
      match_score: m.match_score,
      reasons: m.reasons,
    })),
    note: data.note,
  };
}

const visionService = {
  analyzeRoom,
  getVision,
  getVisionDescription,
  searchByImage,
};

export default visionService;
