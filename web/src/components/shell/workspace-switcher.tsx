"use client";

import { Check, ChevronsUpDown, User, Users } from "lucide-react";
import { useMemo } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/primitives";
import type { Me, Workspace } from "@/lib/api";
import { t } from "@/lib/i18n";
import { useLocalPref } from "@/lib/local-pref";
import { cn } from "@/lib/utils";

const KEY = "cornelius.workspace";

/**
 * Picks the active workspace (personal, or a team's). Stored per browser for
 * now; the library and uploads read it in M1.
 */
export function WorkspaceSwitcher({ me, collapsed }: { me: Me | null; collapsed: boolean }) {
  const workspaces: Workspace[] = useMemo(() => me?.workspaces ?? [], [me]);
  const [savedId, setSavedId] = useLocalPref(KEY, "");
  const activeId =
    (savedId && workspaces.some((w) => w.id === savedId) ? savedId : null) ??
    workspaces.find((w) => w.kind === "personal")?.id ??
    workspaces[0]?.id ??
    null;

  const active = workspaces.find((w) => w.id === activeId) ?? null;
  const label = active ? (active.kind === "personal" ? t("nav.personalWorkspace") : active.name) : t("nav.workspace");
  const Icon = active?.kind === "team" ? Users : User;

  function choose(id: string) {
    setSavedId(id);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "flex h-9 w-full items-center gap-2 rounded-control border border-border bg-bg px-2 text-sm hover:bg-surface",
            collapsed && "justify-center px-0",
          )}
          aria-label={t("nav.workspace")}
          disabled={workspaces.length === 0}
        >
          <Icon className="size-4 shrink-0 text-text-muted" aria-hidden />
          {!collapsed ? (
            <>
              <span className="truncate">{label}</span>
              <ChevronsUpDown className="ml-auto size-3.5 shrink-0 text-text-muted" aria-hidden />
            </>
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        <DropdownMenuLabel>{t("nav.workspace")}</DropdownMenuLabel>
        {workspaces.map((w) => (
          <DropdownMenuItem key={w.id} onSelect={() => choose(w.id)}>
            {w.kind === "team" ? <Users aria-hidden /> : <User aria-hidden />}
            <span className="truncate">{w.kind === "personal" ? t("nav.personalWorkspace") : w.name}</span>
            {w.id === activeId ? <Check className="ml-auto !text-accent" aria-hidden /> : null}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
