/**
 * Legal documents: Markdown files under src/legal/<locale>/ with a version
 * per document. Bump a version when the text changes materially; users are
 * then asked to accept again at their next sign-in (terms and privacy only).
 *
 * The controller is configuration, not text, so moving from a person to a
 * company later is an environment change.
 */
import "server-only";

import { readFile } from "node:fs/promises";
import path from "node:path";

import { marked } from "marked";

import { env } from "@/lib/env";
import { type Locale, defaultLocale } from "@/lib/i18n";
import { PRIVACY_VERSION, TERMS_VERSION } from "@/lib/legal-versions";

export type LegalKind = "terms" | "privacy" | "cookies" | "subprocessors";

export const LEGAL_VERSIONS: Record<LegalKind, { version: string; date: string }> = {
  terms: { version: TERMS_VERSION, date: "16 October 2026" },
  privacy: { version: PRIVACY_VERSION, date: "16 October 2026" },
  cookies: { version: "2026-10-16.1", date: "16 October 2026" },
  subprocessors: { version: "2026-10-16.1", date: "16 October 2026" },
};

export const LEGAL_TITLES: Record<LegalKind, string> = {
  terms: "Terms of Use",
  privacy: "Privacy Notice",
  cookies: "Cookie Notice",
  subprocessors: "Sub-processors",
};

export const LEGAL_KINDS: LegalKind[] = ["terms", "privacy", "cookies", "subprocessors"];

export function controller() {
  return {
    name: process.env.NEXT_PUBLIC_DATA_CONTROLLER_NAME ?? "Stefanos Raptis",
    email: process.env.NEXT_PUBLIC_DATA_CONTROLLER_EMAIL ?? "privacy@example.org",
  };
}

async function readSource(kind: LegalKind, locale: Locale): Promise<string> {
  const base = path.join(process.cwd(), "src", "legal");
  try {
    return await readFile(path.join(base, locale, `${kind}.md`), "utf8");
  } catch {
    return readFile(path.join(base, defaultLocale, `${kind}.md`), "utf8");
  }
}

export async function renderLegal(kind: LegalKind, locale: Locale = defaultLocale): Promise<string> {
  const source = await readSource(kind, locale);
  const c = controller();
  const filled = source.replace(/\{(\w+)\}/g, (match, key: string) => {
    if (key === "app_name") return env.appName;
    if (key === "controller_name") return c.name;
    if (key === "controller_email") return c.email;
    const versionMatch = key.match(/^(\w+)_(version|date)$/);
    if (versionMatch) {
      const [, k, field] = versionMatch;
      const entry = LEGAL_VERSIONS[k as LegalKind];
      if (entry) return field === "version" ? entry.version : entry.date;
    }
    return match;
  });
  return marked.parse(filled, { async: false, gfm: true }) as string;
}
