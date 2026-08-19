// Phase 14 — Vision & content AI: photo intelligence panel for the landlord
// dashboard (analyze → observations/palette/draft, apply suggested tags).
import { useState } from "react";
import { toast } from "sonner";
import { Camera, Check, ClipboardCopy, Loader2, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "../ui/button";
import { useVisionAnalyze, useVisionDescription } from "../../hooks/useVision";
import roomService from "../../services/roomService";
import { getApiErrorMessage } from "../../services/errors";
import type { Room } from "../../types";
import type { VisionAnalysis, VisionDraft } from "../../services/visionService";

interface VisionCardProps {
  room: Room;
}

export default function VisionCard({ room }: VisionCardProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const analyze = useVisionAnalyze();
  const draft = useVisionDescription();
  const [analysis, setAnalysis] = useState<VisionAnalysis | null>(null);
  const [draftData, setDraftData] = useState<VisionDraft | null>(null);
  const [applying, setApplying] = useState(false);

  const handleAnalyze = async () => {
    try {
      const result = await analyze.mutateAsync(room.id);
      if (!result.available) {
        toast.error(result.reason ?? t("vision.noAnalysis"));
        return;
      }
      setAnalysis(result);
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("vision.analyzeError")));
    }
  };

  const handleDraft = async () => {
    try {
      const result = await draft.mutateAsync(room.id);
      setDraftData(result);
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("vision.draftError")));
    }
  };

  const handleApplyTags = async () => {
    if (!analysis || analysis.suggested_amenities.length === 0) return;
    setApplying(true);
    try {
      const merged = [...new Set([...(room.amenities ?? []), ...analysis.suggested_amenities])];
      await roomService.updateRoom(room.id, { amenities: merged });
      await queryClient.invalidateQueries({ queryKey: ["rooms"] });
      toast.success(t("vision.tagsApplied"));
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("vision.applyError")));
    } finally {
      setApplying(false);
    }
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      toast.success(t("vision.copied"));
    } catch {
      toast.error(t("vision.copyError"));
    }
  };

  return (
    <div className="flex w-full flex-col gap-3 rounded-xl border border-gray-200 bg-gray-50/70 p-3 dark:border-gray-800 dark:bg-gray-900/50">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          <Camera className="size-3.5 text-orange-600" />
          {t("vision.photoIntelligence")}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          onClick={handleAnalyze}
          disabled={analyze.isPending}
        >
          {analyze.isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3 text-orange-600" />
          )}
          {analyze.isPending ? t("vision.analyzing") : t("vision.analyze")}
        </Button>
      </div>

      {analysis && (
        <div className="flex flex-col gap-2.5 text-xs text-gray-600 dark:text-gray-400">
          {analysis.caption && (
            <p className="text-[13px] font-medium text-foreground">{analysis.caption}</p>
          )}

          {analysis.palette.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-foreground">{t("vision.palette")}:</span>
              {analysis.palette.slice(0, 5).map((c) => (
                <span
                  key={c.hex}
                  title={`${c.name} (${Math.round(c.share * 100)}%)`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-card px-2 py-0.5 dark:border-gray-700"
                >
                  <span
                    className="size-2.5 rounded-full border border-black/10"
                    style={{ backgroundColor: c.hex }}
                  />
                  {c.name}
                </span>
              ))}
            </div>
          )}

          {analysis.observations.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {analysis.observations.map((o) => (
                <span
                  key={o.kind}
                  className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300"
                >
                  <Check className="size-3" />
                  {o.label}
                </span>
              ))}
            </div>
          )}

          {analysis.suggested_amenities.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-semibold text-foreground">{t("vision.suggestedTags")}:</span>
              {analysis.suggested_amenities.map((a) => (
                <span
                  key={a}
                  className="rounded-full bg-orange-50 px-2 py-0.5 font-medium text-orange-700 dark:bg-orange-950/40 dark:text-orange-300"
                >
                  {a}
                </span>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-6 gap-1 text-xs"
                onClick={handleApplyTags}
                disabled={applying}
              >
                {applying && <Loader2 className="size-3 animate-spin" />}
                {t("vision.applyTags")}
              </Button>
            </div>
          )}

          <p className="text-[11px] leading-snug text-gray-500 dark:text-gray-500">
            {analysis.note}
          </p>
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] text-gray-500 dark:text-gray-500">
          {room.name} · {room.area}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          onClick={handleDraft}
          disabled={draft.isPending}
        >
          {draft.isPending ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <Sparkles className="size-3 text-orange-600" />
          )}
          {draft.isPending ? t("vision.drafting") : t("vision.draftFromPhotos")}
        </Button>
      </div>

      {draftData && (
        <div className="flex flex-col gap-2 rounded-lg border border-orange-200 bg-orange-50/60 p-3 dark:border-orange-900 dark:bg-orange-950/30">
          <div className="flex items-start justify-between gap-2">
            <p className="text-[13px] font-bold text-foreground">{draftData.title}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 gap-1 px-1.5 text-[11px]"
              onClick={() => copyText(draftData.title)}
            >
              <ClipboardCopy className="size-3" />
              {t("vision.copy")}
            </Button>
          </div>
          <p className="text-xs leading-relaxed text-gray-700 dark:text-gray-300">
            {draftData.description}
          </p>
          <div className="flex items-center justify-between gap-2">
            {draftData.amenities.length > 0 && (
              <span className="text-[11px] text-gray-500 dark:text-gray-400">
                {t("vision.suggestedTags")}: {draftData.amenities.join(", ")}
              </span>
            )}
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 gap-1 px-1.5 text-[11px]"
              onClick={() => copyText(draftData.description)}
            >
              <ClipboardCopy className="size-3" />
              {t("vision.copy")}
            </Button>
          </div>
          <p className="text-[11px] text-gray-500 dark:text-gray-500">{draftData.note}</p>
        </div>
      )}
    </div>
  );
}
