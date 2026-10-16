/**
 * Minimal translation layer.
 *
 * All UI strings live in src/messages/<locale>.json. English is the MVP
 * language; adding Greek means adding el.json and listing it below. Keys are
 * dot paths ("auth.signIn") and placeholders are {name}.
 */
import en from "@/messages/en.json";

export type Locale = "en";
export const locales: Locale[] = ["en"];
export const defaultLocale: Locale = "en";

type Messages = typeof en;
const catalogs: Record<Locale, Messages> = { en };

type PathKeys<T, Prefix extends string = ""> = T extends string
  ? Prefix
  : {
      [K in keyof T & string]: PathKeys<T[K], Prefix extends "" ? K : `${Prefix}.${K}`>;
    }[keyof T & string];

export type MessageKey = PathKeys<Messages>;

function lookup(catalog: Messages, key: string): string | undefined {
  let node: unknown = catalog;
  for (const part of key.split(".")) {
    if (node && typeof node === "object" && part in (node as Record<string, unknown>)) {
      node = (node as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return typeof node === "string" ? node : undefined;
}

export function t(
  key: MessageKey,
  params?: Record<string, string | number>,
  locale: Locale = defaultLocale,
): string {
  const template = lookup(catalogs[locale], key) ?? lookup(catalogs.en, key) ?? key;
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) =>
    name in params ? String(params[name]) : `{${name}}`,
  );
}
