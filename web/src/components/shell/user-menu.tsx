"use client";

import { LogOut, Settings, ShieldCheck } from "lucide-react";
import Link from "next/link";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/primitives";
import { t } from "@/lib/i18n";
import { initials } from "@/lib/utils";

export function UserMenu({
  name,
  email,
  secondFactor,
}: {
  name: string;
  email: string | null;
  secondFactor: boolean;
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex size-9 items-center justify-center rounded-full border border-border bg-surface text-xs font-medium"
          aria-label={name || email || "Account"}
        >
          {initials(name || email)}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <DropdownMenuLabel className="normal-case tracking-normal">
          <div className="truncate text-sm font-medium text-text">{name || email}</div>
          {name && email ? <div className="truncate text-xs font-normal text-text-muted">{email}</div> : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/settings">
            <Settings aria-hidden /> {t("nav.settings")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/settings/security">
            <ShieldCheck aria-hidden /> {t("settings.security")}
            {!secondFactor ? <span className="ml-auto text-xs text-warning">{t("common.no")} 2FA</span> : null}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <form action="/auth/signout" method="post">
          <DropdownMenuItem asChild>
            <button type="submit" className="w-full">
              <LogOut aria-hidden /> {t("nav.signOut")}
            </button>
          </DropdownMenuItem>
        </form>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
