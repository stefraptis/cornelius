import Link from "next/link";

import { t } from "@/lib/i18n";

const KINDS = ["terms", "privacy", "cookies", "subprocessors"] as const;

export function LegalLinks() {
  return (
    <nav className="flex flex-wrap gap-3" aria-label={t("footer.legal")}>
      {KINDS.map((k) => (
        <Link key={k} href={`/legal/${k}`} className="hover:text-text">
          {t(`legal.${k}`)}
        </Link>
      ))}
    </nav>
  );
}
