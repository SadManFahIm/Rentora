import { useEffect, useState } from "react";
import { Bell, BellOff } from "lucide-react";
import { toast } from "sonner";
import { env } from "../../config/env";
import { disablePush, enablePush, hasPushSubscription } from "../../services/pushService";
import { Button } from "../ui/button";

/** Browser push-notification toggle (Phase 10). */
export default function PushNotificationCard() {
  const [enabled, setEnabled] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    hasPushSubscription().then((active) => {
      if (mounted) {
        setEnabled(active);
        setLoading(false);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  const toggle = async () => {
    if (!env.VAPID_PUBLIC_KEY) {
      toast.info("Push notifications aren't configured for this environment yet.");
      return;
    }
    setLoading(true);
    try {
      if (enabled) {
        await disablePush();
        setEnabled(false);
        toast.success("Browser notifications off");
      } else {
        const ok = await enablePush();
        if (!ok) {
          toast.error(
            "Could not enable notifications — check the browser's notification permission."
          );
        } else {
          setEnabled(true);
          toast.success("Browser notifications on — you'll hear about bookings, chats & deals");
        }
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
      <div className="flex items-center gap-2">
        {enabled ? (
          <Bell className="size-4 text-orange-600" />
        ) : (
          <BellOff className="size-4 text-gray-500" />
        )}
        <h3 className="font-display text-sm font-bold text-foreground">Browser notifications</h3>
      </div>
      <p className="mb-3 mt-1 text-xs text-gray-600 dark:text-gray-400">
        {enabled
          ? "You're subscribed — booking updates, chat messages and price drops arrive even when Rentora is closed."
          : "Get booking updates, chat messages and price drops even when Rentora is closed."}
      </p>
      <Button
        variant={enabled ? "outline" : "default"}
        size="sm"
        className={
          enabled ? "rounded-lg" : "rounded-lg bg-orange-600 text-white hover:bg-orange-700"
        }
        disabled={loading}
        onClick={toggle}
      >
        {loading ? "Checking…" : enabled ? "Turn off" : "Turn on"}
      </Button>
    </div>
  );
}
