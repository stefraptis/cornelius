import Link from "next/link";

import { Logo } from "@/components/shell/logo";
import { t } from "@/lib/i18n";

/** Public pages: legal documents. No sign-in required. */
export default function PublicLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 items-center border-b border-border px-6">
        <Link href="/" className="flex items-center gap-2 text-sm font-medium">
          <Logo className="size-5" />
          {t("app.name")}
        </Link>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">{children}</main>
      <footer className="border-t border-border px-6 py-4 text-xs text-text-muted">{t("app.positioning")}</footer>
    </div>
  );
}
