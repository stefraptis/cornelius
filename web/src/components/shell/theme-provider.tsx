"use client";

/**
 * Light and dark theme without a third-party provider.
 *
 * The choice ("light", "dark" or "system") is a per-browser preference. The
 * <html> element gets the "dark" class when the resolved theme is dark. A
 * small inline script in the root layout (themeInitScript) applies the class
 * before the first paint so there is no flash; this provider keeps it in sync
 * afterwards and follows the system setting when "system" is selected.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useSyncExternalStore } from "react";

import { useLocalPref } from "@/lib/local-pref";

export type Theme = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_KEY = "cornelius.theme";

/** Runs before hydration. Keep it tiny and dependency-free. */
export const themeInitScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(THEME_KEY)});var d=t==="dark"||((!t||t==="system")&&window.matchMedia("(prefers-color-scheme: dark)").matches);var c=document.documentElement.classList;d?c.add("dark"):c.remove("dark");}catch(e){}})();`;

type ThemeContextValue = {
  theme: Theme;
  resolvedTheme: ResolvedTheme;
  setTheme: (theme: Theme) => void;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

const query = "(prefers-color-scheme: dark)";

function subscribeSystem(callback: () => void) {
  const media = window.matchMedia(query);
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
}

function useSystemPrefersDark(): boolean {
  return useSyncExternalStore(
    subscribeSystem,
    () => window.matchMedia(query).matches,
    () => false,
  );
}

function isTheme(value: string): value is Theme {
  return value === "light" || value === "dark" || value === "system";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [stored, setStored] = useLocalPref(THEME_KEY, "system");
  const theme: Theme = isTheme(stored) ? stored : "system";
  const systemDark = useSystemPrefersDark();
  const resolvedTheme: ResolvedTheme = theme === "system" ? (systemDark ? "dark" : "light") : theme;

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", resolvedTheme === "dark");
    root.style.colorScheme = resolvedTheme;
  }, [resolvedTheme]);

  const setTheme = useCallback((next: Theme) => setStored(next), [setStored]);
  const value = useMemo(() => ({ theme, resolvedTheme, setTheme }), [theme, resolvedTheme, setTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (!context) throw new Error("useTheme must be used inside ThemeProvider");
  return context;
}
