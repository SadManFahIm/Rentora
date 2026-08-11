import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Share2 } from "lucide-react";
import { toast } from "sonner";
import wishlistService from "../../services/wishlistService";
import { Button } from "../ui/button";

/** Share-my-wishlist button — copies the public link + social shortcuts (Phase 10). */
export default function WishlistShareButton() {
  const { data: shareInfo } = useQuery({
    queryKey: ["wishlist-share-info"],
    queryFn: wishlistService.getShareInfo,
  });
  const [copied, setCopied] = useState(false);

  if (!shareInfo) return null;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareInfo.link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Could not copy link");
    }
  };

  return (
    <Button variant="outline" size="sm" className="rounded-lg" onClick={copy}>
      <Share2 className="size-4" />
      {copied ? "Copied!" : "Share wishlist"}
    </Button>
  );
}
