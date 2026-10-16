import { cn } from "@/lib/utils";

/**
 * Placeholder mark until the product name and logo are decided: a quiet
 * timeline glyph (three phase segments) in the current text color.
 */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={cn("text-text", className)} aria-hidden>
      <rect x="2" y="10" width="7" height="4" rx="1" fill="currentColor" />
      <rect x="10" y="10" width="4" height="4" rx="1" fill="currentColor" opacity="0.55" />
      <rect x="15" y="10" width="7" height="4" rx="1" fill="currentColor" opacity="0.3" />
      <rect x="2" y="17" width="20" height="1.5" rx="0.75" fill="currentColor" opacity="0.4" />
    </svg>
  );
}
