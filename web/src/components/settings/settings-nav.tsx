"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { t } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/settings", label: t("settings.profile") },
  { href: "/settings/security", label: t("settings.security") },
  { href: "/settings/privacy", label: t("settings.privacy") },
];

export function SettingsNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-1 md:flex-col" aria-label={t("settings.title")}>
      {ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "rounded-control px-3 py-2 text-sm text-text-muted hover:bg-surface hover:text-text",
              active && "bg-surface font-medium text-text",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
