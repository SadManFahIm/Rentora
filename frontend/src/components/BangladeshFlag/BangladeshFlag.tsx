import { cn } from "../../lib/utils";

/**
 * Inline SVG Bangladesh flag 🇧🇩 — renders identically on every OS/browser
 * (the country-flag EMOJI shows as "BD" letters on some Windows setups, so we
 * never depend on it for the brand). Aspect ratio 10:6 per the official flag.
 */
export default function BangladeshFlag({
  className,
  title = "Bangladesh",
}: {
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 10 6"
      role="img"
      aria-label={title}
      className={cn(
        "inline-block h-[1em] w-auto align-[-0.125em] rounded-[1px] shadow-[0_0_1px_rgba(0,0,0,0.4)]",
        className
      )}
    >
      <title>{title}</title>
      <rect width="10" height="6" fill="#006a4e" />
      <circle cx="4.35" cy="3" r="1.55" fill="#f42a41" />
    </svg>
  );
}
