import { Download } from "lucide-react";
import { usePwaInstall } from "../../hooks/usePwaInstall";
import { Button } from "../ui/button";

/**
 * Subtle "Install Rentora" CTA.
 *
 * Only appears when the browser offers an install prompt AND the app is not
 * already installed AND the user hasn't dismissed it this week. Clicking shows
 * the browser's native prompt (never a fake popup). Once installed it
 * disappears for good.
 */
export default function PwaInstallPrompt() {
  const { canInstall, promptInstall } = usePwaInstall();
  if (!canInstall) return null;

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={() => void promptInstall()}
      className="hidden items-center gap-1.5 md:inline-flex"
      aria-label="Install Rentora as an app"
    >
      <Download className="h-4 w-4" aria-hidden />
      <span>Install app</span>
    </Button>
  );
}
