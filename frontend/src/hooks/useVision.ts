import { useMutation } from "@tanstack/react-query";
import visionService, {
  type VisionAnalysis,
  type VisionDraft,
  type VisionSearchResult,
} from "../services/visionService";

/** Phase 14 — vision & content AI hooks (photo intelligence). */

export function useVisionAnalyze() {
  return useMutation({
    mutationFn: (roomId: number) => visionService.analyzeRoom(roomId),
  });
}

export function useVisionDescription() {
  return useMutation({
    mutationFn: (roomId: number) => visionService.getVisionDescription(roomId),
  });
}

export function useImageSearch() {
  return useMutation({
    mutationFn: (file: File) => visionService.searchByImage(file),
  });
}

export type { VisionAnalysis, VisionDraft, VisionSearchResult };
