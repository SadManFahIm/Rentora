import { useState } from "react";
import {
  ArrowRight,
  BadgeCheck,
  Flag,
  Images,
  MessageSquareWarning,
  Scale,
  ScrollText,
  ShieldCheck,
} from "lucide-react";
import { useKycSla, usePendingTenantKycApplications } from "../../hooks/useKyc";
import { useModerationOverview } from "../../hooks/useModeration";
import { useAdminReports, useChatSafetyEvents } from "../../hooks/useChat";
import { useAdminDisputes } from "../../hooks/useDisputes";
import { useAuditTrail } from "../../hooks/useAudit";
import { cn } from "../../lib/utils";
import AdminKycPanel from "../AdminKycPanel/AdminKycPanel";
import AdminReportsPanel from "../AdminReportsPanel/AdminReportsPanel";
import AdminModerationPanel from "../AdminModerationPanel/AdminModerationPanel";
import AdminDisputesPanel from "../AdminDisputesPanel/AdminDisputesPanel";
import { AuditTrailTab } from "./AuditTrailTab";
import { ChatSafetyFeed } from "./ChatSafetyFeed";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "kyc", label: "KYC" },
  { id: "chat", label: "Chat Safety" },
  { id: "reports", label: "Reports" },
  { id: "moderation", label: "Moderation" },
  { id: "disputes", label: "Disputes" },
  { id: "audit", label: "Audit Trail" },
] as const;

type TabId = (typeof TABS)[number]["id"];

function OverviewCard({
  icon,
  label,
  value,
  detail,
  onOpen,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  detail: string;
  onOpen: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex flex-col items-start gap-2 rounded-2xl border border-gray-200 bg-card p-5 text-left transition-colors hover:border-orange-400/60 dark:border-gray-800 dark:hover:border-orange-500/40"
    >
      <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">{icon}</div>
      <div>
        <div className="font-display text-3xl font-bold text-foreground">{value}</div>
        <div className="text-sm text-gray-600 dark:text-gray-400">{label}</div>
      </div>
      <div className="flex w-full items-center justify-between">
        <span className="text-xs text-gray-500 dark:text-gray-500">{detail}</span>
        <ArrowRight className="size-3.5 text-gray-400 transition-transform group-hover:translate-x-0.5 group-hover:text-orange-500" />
      </div>
    </button>
  );
}

/** Unified Trust & Safety Operations Center (Phase 12). One entry point for
 * every moderation queue: identity (KYC), content (reports + moderation),
 * behavior (chat safety), and disputes — with a single audit trail. */
export default function AdminTrustCenter() {
  const [tab, setTab] = useState<TabId>("overview");

  const { data: kycSla } = useKycSla();
  const { data: tenantPending = [] } = usePendingTenantKycApplications();
  const { data: safetyEvents = [] } = useChatSafetyEvents();
  const { data: reports = [] } = useAdminReports("all");
  const { data: moderation } = useModerationOverview();
  const { data: openDisputes = [] } = useAdminDisputes("open");
  const { data: audit = [] } = useAuditTrail();

  const openReports = reports.filter(
    (r) => r.status === "open" || r.status === "under_review"
  ).length;
  const pendingModeration =
    (moderation?.reviewsPending ?? 0) +
    (moderation?.reviewsFlagged ?? 0) +
    (moderation?.photosPending ?? 0) +
    (moderation?.photosFlagged ?? 0);
  const kycPending = (kycSla?.pendingCount ?? 0) + tenantPending.length;

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center gap-2">
        <ShieldCheck className="size-5 text-orange-600" />
        <div>
          <h2 className="font-display text-lg font-bold text-foreground">
            Trust & Safety Operations Center
          </h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            One dashboard for identity, content, behavior and disputes — every decision is audited.
          </p>
        </div>
      </div>

      {/* Sub-tabs */}
      <div className="flex w-fit max-w-full flex-wrap gap-1 rounded-xl bg-gray-50 p-1 dark:bg-gray-800">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={cn(
              "rounded-lg px-4 py-1.5 text-sm font-medium capitalize transition-colors",
              tab === t.id
                ? "bg-card text-foreground shadow-sm"
                : "text-gray-600 hover:text-foreground dark:text-gray-400"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <OverviewCard
            icon={<BadgeCheck className="size-5" />}
            label="KYC pending"
            value={kycPending}
            detail="landlord + tenant verification queues"
            onOpen={() => setTab("kyc")}
          />
          <OverviewCard
            icon={<MessageSquareWarning className="size-5" />}
            label="Chat safety events"
            value={safetyEvents.length}
            detail="warned / flagged / blocked messages"
            onOpen={() => setTab("chat")}
          />
          <OverviewCard
            icon={<Flag className="size-5" />}
            label="Open reports"
            value={openReports}
            detail="user & message reports awaiting review"
            onOpen={() => setTab("reports")}
          />
          <OverviewCard
            icon={<Images className="size-5" />}
            label="Moderation pending"
            value={pendingModeration}
            detail="reviews + photos in the queue"
            onOpen={() => setTab("moderation")}
          />
          <OverviewCard
            icon={<Scale className="size-5" />}
            label="Open disputes"
            value={openDisputes.length}
            detail="booking disputes in progress"
            onOpen={() => setTab("disputes")}
          />
          <OverviewCard
            icon={<ScrollText className="size-5" />}
            label="Audit entries"
            value={audit.length}
            detail="append-only trail of admin actions"
            onOpen={() => setTab("audit")}
          />
        </div>
      )}

      {tab === "kyc" && <AdminKycPanel />}
      {tab === "chat" && <ChatSafetyFeed />}
      {tab === "reports" && <AdminReportsPanel />}
      {tab === "moderation" && <AdminModerationPanel />}
      {tab === "disputes" && <AdminDisputesPanel />}
      {tab === "audit" && <AuditTrailTab />}
    </div>
  );
}
