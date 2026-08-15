import { useState } from "react";
import {
  AlertCircle,
  BadgeCheck,
  Clock,
  FileUp,
  Loader2,
  ShieldCheck,
  UploadCloud,
} from "lucide-react";
import { toast } from "sonner";
import { useMyTenantVerification, useSubmitTenantVerification } from "../../hooks/useKyc";
import { getApiErrorMessage } from "../../services/errors";
import type { KycDocType } from "../../types";
import { cn } from "../../lib/utils";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";

const DOC_TYPES: { value: KycDocType; label: string }[] = [
  { value: "nid", label: "National ID (NID)" },
  { value: "passport", label: "Passport" },
];

const statusClasses: Record<string, string> = {
  pending: "bg-amber-500/10 text-amber-500",
  verified: "bg-emerald-500/10 text-emerald-500",
  rejected: "bg-red-500/10 text-red-500",
  needs_review: "bg-amber-500/10 text-amber-500",
  expired: "bg-gray-100 text-gray-500 dark:bg-gray-800",
};

const STATUS_COPY: Record<string, string> = {
  verified:
    "Verified — landlords see the verified-tenant badge when you inquire or book. Identity verification lasts one year.",
  pending: "Your document is under review. This usually takes under a day.",
  rejected:
    "Your document was not approved. Review the note below, then upload a clear copy to try again.",
  needs_review: "Your document needs attention. Review the note below, then upload a clear copy.",
  expired: "Your previous verification expired. Upload a fresh document to verify again.",
};

export default function TenantKycCard() {
  const { data: verification, isLoading } = useMyTenantVerification();
  const submit = useSubmitTenantVerification();

  const [docType, setDocType] = useState<KycDocType>("nid");
  const [file, setFile] = useState<File | null>(null);

  const status = verification?.status ?? "not_started";
  const verified = status === "verified";
  const pending = status === "pending";
  // Any state that needs (or allows) a fresh submission: not started,
  // rejected, expired, needs review.
  const canSubmit = !verified && !pending;
  const note = verification?.reviewNote?.trim();

  const submitFile = async () => {
    if (!file) return;
    try {
      await submit.mutateAsync({ docType, file });
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
          <h3 className="font-display text-sm font-bold text-foreground">Tenant Verification</h3>
          <p className="mt-0.5 text-sm text-gray-600 dark:text-gray-400">
            {verified
              ? STATUS_COPY.verified
              : pending
                ? STATUS_COPY.pending
                : (STATUS_COPY[status] ??
                  "Verify your identity so landlords can trust you when you inquire or book.")}
          </p>
        </div>
        {verified && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs font-semibold text-emerald-500">
            <BadgeCheck className="size-3" /> Verified
          </span>
        )}
        {pending && (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-0.5 text-xs font-semibold text-amber-500">
            <Clock className="size-3" /> Reviewing
          </span>
        )}
      </div>

      {/* Reviewer note banner — shown for rejected / needs_review. */}
      {!verified && !pending && note && (
        <div className="mt-4 flex gap-2.5 rounded-xl border border-red-200 bg-red-50 p-3.5 text-sm dark:border-red-500/30 dark:bg-red-500/10">
          <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-500" />
          <div>
            <p className="font-semibold text-red-600 dark:text-red-400">Reviewer note</p>
            <p className="mt-0.5 text-red-600/90 dark:text-red-400/80">“{note}”</p>
          </div>
        </div>
      )}

      {canSubmit && (
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
            aria-label="Tenant verification document file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button
            className="shrink-0 bg-orange-600 text-white hover:bg-orange-700"
            onClick={submitFile}
            disabled={!file || submit.isPending}
          >
            {submit.isPending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <UploadCloud className="size-4" />
            )}
            {status === "not_started" ? "Submit" : "Re-submit"}
          </Button>
        </div>
      )}

      {isLoading && <p className="mt-4 text-sm text-gray-500">Loading verification status…</p>}

      {/* Submitted document summary (owner-only view). */}
      {!isLoading && verification && !canSubmit && (
        <ul className="mt-4 space-y-2">
          <li className="flex items-center justify-between gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-sm dark:border-gray-800 dark:bg-gray-800/50">
            <span className="flex items-center gap-2 text-gray-700 dark:text-gray-300">
              <FileUp className="size-4 text-gray-500" />
              {verification.docTypeDisplay}
            </span>
            <span
              className={cn(
                "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold",
                statusClasses[status]
              )}
            >
              {verification.statusDisplay}
            </span>
          </li>
        </ul>
      )}
    </div>
  );
}
