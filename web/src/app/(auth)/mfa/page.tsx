import type { Metadata } from "next";
import { Suspense } from "react";

import { MfaChallenge } from "@/components/auth/mfa-challenge";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("auth.mfa.title") };

export default function MfaPage() {
  return (
    <Suspense>
      <MfaChallenge />
    </Suspense>
  );
}
