import Link from "next/link";

import { Logo } from "@/components/shell/logo";
import { t } from "@/lib/i18n";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <header className="flex h-14 items-center border-b border-border px-6">
        <Link href="/" className="flex items-center gap-2 text-sm font-medium">
          <Logo className="size-5" />
          {t("app.name")}
        </Link>
      </header>
      <main className="flex flex-1 items-start justify-center px-4 py-12 sm:py-20">
        <div className="w-full max-w-sm">{children}</div>
      </main>
      <footer className="border-t border-border px-6 py-4 text-xs text-text-muted">
        {t("app.positioning")}
      </footer>
    </div>
  );
}
