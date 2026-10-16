"use client";

import { Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/primitives";
import { type Theme, useTheme } from "@/components/shell/theme-provider";
import { t } from "@/lib/i18n";
import { useMounted } from "@/lib/local-pref";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const mounted = useMounted();

  const Icon = !mounted ? Monitor : resolvedTheme === "dark" ? Moon : Sun;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t("nav.theme")}>
          <Icon aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as Theme)}>
          <DropdownMenuRadioItem value="light">
            <Sun aria-hidden /> {t("nav.themeLight")}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark">
            <Moon aria-hidden /> {t("nav.themeDark")}
          </DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system">
            <Monitor aria-hidden /> {t("nav.themeSystem")}
          </DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
