import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

// ---------- Status chip ----------

export type ChipTone = "neutral" | "accent" | "warning" | "danger";

const chipTones: Record<ChipTone, string> = {
  neutral: "border-border text-text-muted",
  accent: "border-accent/40 text-accent",
  warning: "border-warning/50 text-warning",
  danger: "border-danger/50 text-danger",
};

export function Chip({
  tone = "neutral",
  className,
  children,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { tone?: ChipTone }) {
  return (
    <span
      className={cn(
        "inline-flex h-6 items-center gap-1.5 rounded-full border px-2 text-xs font-medium",
        chipTones[tone],
        className,
      )}
      {...props}
    >
      {children}
    </span>
  );
}

// ---------- Stat tile ----------

export function StatTile({
  label,
  value,
  unit,
  hint,
  tone = "neutral",
  className,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  hint?: string;
  tone?: ChipTone;
  className?: string;
}) {
  return (
    <div className={cn("rounded-panel border border-border bg-surface p-4", className)}>
      <div className="text-xs font-medium uppercase tracking-wide text-text-muted">{label}</div>
      <div
        className={cn(
          "mt-2 font-mono text-xl tabular",
          tone === "danger" && "text-danger",
          tone === "warning" && "text-warning",
          tone === "accent" && "text-accent",
        )}
      >
        {value}
        {unit ? <span className="ml-1 text-sm text-text-muted">{unit}</span> : null}
      </div>
      {hint ? <div className="mt-1 text-xs text-text-muted">{hint}</div> : null}
    </div>
  );
}

// ---------- Panel ----------

export function Panel({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-panel border border-border bg-bg", className)} {...props} />;
}

export function PanelHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-start justify-between gap-4 border-b border-border px-5 py-4", className)}>
      <div>
        <h2 className="text-base font-medium">{title}</h2>
        {description ? <p className="mt-0.5 text-sm text-text-muted">{description}</p> : null}
      </div>
      {actions}
    </div>
  );
}

// ---------- Empty state ----------

export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  className,
}: {
  icon?: LucideIcon;
  title: string;
  body?: string;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-panel border border-dashed border-border px-6 py-16 text-center",
        className,
      )}
    >
      {Icon ? <Icon className="mb-4 size-8 text-text-muted" strokeWidth={1.5} aria-hidden /> : null}
      <h3 className="text-base font-medium">{title}</h3>
      {body ? <p className="mt-1 max-w-md text-sm text-text-muted">{body}</p> : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

// ---------- Skeleton ----------

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-control bg-surface", className)} aria-hidden {...props} />;
}

// ---------- Page header ----------

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

// ---------- Color swatch (data colors) ----------

export function Swatch({ color, label, className }: { color: string; label: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 text-sm", className)}>
      <span className="size-3 shrink-0 rounded-[3px]" style={{ backgroundColor: color }} aria-hidden />
      {label}
    </span>
  );
}
