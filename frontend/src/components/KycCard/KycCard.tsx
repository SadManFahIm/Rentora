import { useState } from "react";
import { BadgeCheck, FileUp, Loader2, ShieldCheck, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import { useMyKycDocuments, useUploadKycDocument } from "../../hooks/useKyc";
import { useApp } from "../../context/AppContext";
import { getApiErrorMessage } from "../../services/errors";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import type { KycDocType } from "../../types";
import { cn } from "../../lib/utils";

const DOC_TYPES: { value: KycDocType; label: string }[] = [
  { value: "nid", label: "National ID (NID)" },
  { value: "passport", label: "Passport" },
];

const statusClasses: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-500",
  approved: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-red-500/10 text-red-500",
};

export default function KycCard() {
  const { user } = useApp();
  const { data: documents = [], isLoading } = useMyKycDocuments();
  const upload = useUploadKycDocument();

  const [docType, setDocType] = useState<KycDocType>("nid");
  const [file, setFile] = useState<File | null>(null);

  const verified = user?.nidVerified === true;
  const pending = documents.some((d) => d.status === "pending");

  const submit = async () => {
    if (!file) return;
    try {
      await upload.mutateAsync({ docType, file });
      toast.success("Document uploaded — we'll review it shortly.");
      setFile(null);
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Upload failed. Try again."));
    }
  };

  return (
    <div className="rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
      <div className="flex items-start gap-3">
        <span
          className={cn(
            "inline-flex size-10 shrink-0 items-center justify-center rounded-xl",
            verified
              ? "bg-emerald-500/10 text-emerald-500"
              : "bg-gray-100 text-gray-500 dark:bg-gray-800"
          )}
        >
          <ShieldCheck className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-sm font-bold text-foreground">
            Identity Verification (KYC)
          </h3>
          <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
            {verified
              ? "Verified — your listings carry the trust badge and rank above unverified landlords."
              : pending
                ? "Your document is under review. This usually takes under a day."
                : "Upload your NID or passport to get the verified badge on your listings."}
          </p>
        </div>
        {verified && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-500">
            <BadgeCheck className="size-3" /> Verified
          </span>
        )}
      </div>

      {!verified && (
        <>
          {/* Upload form (hidden once something is pending review). */}
          {!pending && (
            <div className="mt-4 flex flex-col gap-2.5 sm:flex-row sm:items-center">
              <Select value={docType} onValueChange={(v) => setDocType(v as KycDocType)}>
                <SelectTrigger className="w-full sm:w-52">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {DOC_TYPES.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Input
                type="file"
                accept="image/*,.pdf"
                className="flex-1"
                aria-label="KYC document file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
              <Button
                className="shrink-0 bg-orange-600 text-white hover:bg-orange-700"
                onClick={submit}
                disabled={!file || upload.isPending}
              >
                {upload.isPending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <UploadCloud className="size-4" />
                )}
                Upload
              </Button>
            </div>
          )}

          {/* Submitted documents with their status. */}
          {isLoading ? (
            <p className="mt-4 text-sm text-gray-500">Loading documents…</p>
          ) : documents.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm dark:border-gray-800 dark:bg-gray-800/50"
                >
                  <span className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
                    <FileUp className="size-4 text-gray-500" />
                    {doc.docTypeDisplay}
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
                      statusClasses[doc.status]
                    )}
                  >
                    {doc.statusDisplay}
                  </span>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
}
