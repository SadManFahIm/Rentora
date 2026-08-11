import { useState } from "react";
import { Copy, Gift, Users } from "lucide-react";
import { toast } from "sonner";
import { useReferral } from "../../hooks/useReferral";
import { Button } from "../ui/button";

/** Referral invite card — code, share link, invited count (Phase 10). */
export default function ReferralCard() {
  const { data: referral, isLoading } = useReferral();
  const [copied, setCopied] = useState(false);

  if (isLoading || !referral) return null;

  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(referral.link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy link");
    }
  };

  const shareTargets = [
    {
      label: "WhatsApp",
      url: `https://wa.me/?text=${encodeURIComponent(`Find your next room on Rentora! ${referral.link}`)}`,
      icon: "💬",
    },
    {
      label: "Facebook",
      url: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(referral.link)}`,
      icon: "📘",
    },
  ];

  return (
    <div className="rounded-xl border border-orange-200 bg-orange-50/40 p-4 dark:border-orange-900/40 dark:bg-orange-950/10">
      <div className="mb-2 flex items-center gap-2">
        <Gift className="size-4 text-orange-600" />
        <h3 className="font-display text-sm font-bold text-foreground">Invite friends</h3>
        <span className="ml-auto flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
          <Users className="size-3.5" /> {referral.invitedCount} joined
        </span>
      </div>
      <p className="mb-3 text-xs text-gray-600 dark:text-gray-400">
        Share your link — every friend who joins gets room-hunting on Rentora, and your invitations
        show up here.
      </p>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" className="flex-1 rounded-lg" onClick={copyLink}>
          <Copy className="size-3.5" />
          {copied ? "Copied!" : "Copy invite link"}
        </Button>
        {shareTargets.map((t) => (
          <a
            key={t.label}
            href={t.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-lg border border-gray-300 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-orange-500 dark:border-gray-600"
          >
            {t.icon} {t.label}
          </a>
        ))}
      </div>
    </div>
  );
}
