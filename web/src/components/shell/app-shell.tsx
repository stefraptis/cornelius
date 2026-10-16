"use client";

import {
  Activity,
  BarChart3,
  ChevronsLeft,
  ChevronsRight,
  Cpu,
  FolderOpen,
  GraduationCap,
  Settings,
  Tags,
  Users,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { FeedbackButton } from "@/components/shell/feedback-button";
import { Logo } from "@/components/shell/logo";
import { ThemeToggle } from "@/components/shell/theme-toggle";
import { UsageTracker } from "@/components/shell/usage-tracker";
import { UserMenu } from "@/components/shell/user-menu";
import { WorkspaceSwitcher } from "@/components/shell/workspace-switcher";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/primitives";
import type { Me } from "@/lib/api";
import { t, type MessageKey } from "@/lib/i18n";
import { useLocalPref } from "@/lib/local-pref";
import { cn } from "@/lib/utils";

const NAV: { href: string; labelKey: MessageKey; icon: typeof FolderOpen }[] = [
  { href: "/library", labelKey: "nav.library", icon: FolderOpen },
  { href: "/analytics", labelKey: "nav.analytics", icon: BarChart3 },
  { href: "/quizzes", labelKey: "nav.quizzes", icon: GraduationCap },
  { href: "/annotation", labelKey: "nav.annotation", icon: Tags },
  { href: "/teams", labelKey: "nav.teams", icon: Users },
  { href: "/settings", labelKey: "nav.settings", icon: Settings },
];

const COLLAPSED_KEY = "cornelius.sidebar.collapsed";

export function AppShell({
  me,
  fallback,
  apiError,
  children,
}: {
  me: Me | null;
  fallback: { email: string | null; fullName: string };
  apiError: string | null;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [collapsedPref, setCollapsedPref] = useLocalPref(COLLAPSED_KEY, "0");
  const collapsed = collapsedPref === "1";

  function toggle() {
    setCollapsedPref(collapsed ? "0" : "1");
  }

  const displayName = me?.profile.full_name || fallback.fullName || fallback.email || "";
  const email = me?.email ?? fallback.email;

  return (
    <div className="flex min-h-dvh">
      <aside
        className={cn(
          "sticky top-0 flex h-dvh shrink-0 flex-col border-r border-border bg-surface transition-[width] duration-150",
          collapsed ? "w-14" : "w-60",
        )}
      >
        <div className={cn("flex h-14 items-center gap-2 border-b border-border px-3", collapsed && "justify-center")}>
          <Logo className="size-5 shrink-0" />
          {!collapsed ? <span className="truncate text-sm font-medium">{t("app.name")}</span> : null}
        </div>

        <div className="border-b border-border p-2">
          <WorkspaceSwitcher me={me} collapsed={collapsed} />
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 p-2" aria-label="Main">
          {NAV.map(({ href, labelKey, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(href + "/");
            const label = t(labelKey);
            const link = (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex h-9 items-center gap-3 rounded-control px-2.5 text-sm text-text-muted transition-colors hover:bg-bg hover:text-text",
                  active && "bg-bg text-text font-medium shadow-[inset_2px_0_0_var(--accent)]",
                  collapsed && "justify-center px-0",
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden />
                {!collapsed ? <span className="truncate">{label}</span> : <span className="sr-only">{label}</span>}
              </Link>
            );
            return collapsed ? (
              <Tooltip key={href}>
                <TooltipTrigger asChild>{link}</TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            ) : (
              link
            );
          })}
        </nav>

        <div className="flex flex-col gap-0.5 border-t border-border p-2">
          {me?.platform_admin ? (
            <Link
              href="/admin/usage"
              className={cn(
                "flex h-9 items-center gap-3 rounded-control px-2.5 text-sm text-text-muted hover:bg-bg hover:text-text",
                pathname.startsWith("/admin") && "bg-bg text-text font-medium",
                collapsed && "justify-center px-0",
              )}
            >
              <Activity className="size-4 shrink-0" aria-hidden />
              {!collapsed ? t("nav.admin") : <span className="sr-only">{t("nav.admin")}</span>}
            </Link>
          ) : null}
          <Link
            href="/about-model"
            className={cn(
              "flex h-9 items-center gap-3 rounded-control px-2.5 text-sm text-text-muted hover:bg-bg hover:text-text",
              pathname === "/about-model" && "bg-bg text-text font-medium",
              collapsed && "justify-center px-0",
            )}
          >
            <Cpu className="size-4 shrink-0" aria-hidden />
            {!collapsed ? t("nav.aboutModel") : <span className="sr-only">{t("nav.aboutModel")}</span>}
          </Link>
          <button
            type="button"
            onClick={toggle}
            className={cn(
              "flex h-9 items-center gap-3 rounded-control px-2.5 text-sm text-text-muted hover:bg-bg hover:text-text",
              collapsed && "justify-center px-0",
            )}
            aria-label={collapsed ? t("nav.expand") : t("nav.collapse")}
          >
            {collapsed ? <ChevronsRight className="size-4" aria-hidden /> : <ChevronsLeft className="size-4" aria-hidden />}
            {!collapsed ? t("nav.collapse") : null}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-14 items-center justify-end gap-2 border-b border-border bg-bg px-4">
          {apiError ? (
            <span className="mr-auto rounded-control border border-warning/50 px-2 py-1 text-xs text-warning" role="status">
              API unavailable: {apiError}
            </span>
          ) : null}
          <FeedbackButton />
          <ThemeToggle />
          <UserMenu name={displayName} email={email} secondFactor={me?.second_factor ?? false} />
        </header>
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-6">{children}</main>
        <UsageTracker />
        <footer className="border-t border-border px-6 py-3 text-xs text-text-muted">{t("footer.disclaimer")}</footer>
      </div>
    </div>
  );
}
