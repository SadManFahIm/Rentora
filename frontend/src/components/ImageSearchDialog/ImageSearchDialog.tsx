// Phase 14 — AI image search: upload a room photo, get look-alike listings.
import { useRef, useState } from "react";
import { toast } from "sonner";
import { Camera, ImagePlus, Loader2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "../ui/button";
import { useImageSearch } from "../../hooks/useVision";
import { getApiErrorMessage } from "../../services/errors";
import type { VisionMatch } from "../../services/visionService";

interface ImageSearchDialogProps {
  open: boolean;
  onClose: () => void;
  onResult: (matches: VisionMatch[]) => void;
}

export default function ImageSearchDialog({ open, onClose, onResult }: ImageSearchDialogProps) {
  const { t } = useTranslation();
  const search = useImageSearch();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  if (!open) return null;

  const handleFile = (f: File | undefined) => {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
  };

  const handleSearch = async () => {
    if (!file) return;
    try {
      const result = await search.mutateAsync(file);
      onResult(result.matches);
      onClose();
      setFile(null);
      setPreview(null);
    } catch (err) {
      toast.error(getApiErrorMessage(err, t("vision.searchError")));
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl border border-gray-200 bg-card p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={t("vision.imageSearch")}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 font-display text-base font-bold text-foreground">
            <Camera className="size-4 text-orange-600" />
            {t("vision.imageSearch")}
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-1 text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <X className="size-4" />
          </button>
        </div>

        <p className="mb-4 text-sm text-gray-600 dark:text-gray-400">{t("vision.uploadHint")}</p>

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-gray-300 bg-gray-50 py-8 text-gray-500 transition hover:border-orange-400 hover:bg-orange-50/50 dark:border-gray-700 dark:bg-gray-900/50 dark:hover:border-orange-600"
        >
          {preview ? (
            <img
              src={preview}
              alt="Selected room photo"
              className="max-h-48 rounded-lg object-contain"
            />
          ) : (
            <>
              <ImagePlus className="size-8 text-orange-600" />
              <span className="text-sm font-medium">{t("vision.choosePhoto")}</span>
            </>
          )}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => handleFile(e.target.files?.[0])}
        />

        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose}>
            {t("vision.cancel")}
          </Button>
          <Button type="button" onClick={handleSearch} disabled={!file || search.isPending}>
            {search.isPending && <Loader2 className="size-4 animate-spin" />}
            {search.isPending ? t("vision.searching") : t("vision.searchByPhoto")}
          </Button>
        </div>
      </div>
    </div>
  );
}
