"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/library";
  return value;
}

/** Second step of sign-in for users with a verified TOTP factor. */
export function MfaChallenge() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const supabase = createClient();

  const [factorId, setFactorId] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const { data } = await supabase.auth.mfa.listFactors();
      const totp: { id: string; status: string }[] = data?.totp ?? [];
      const factor = totp.find((f) => f.status === "verified") ?? totp[0];
      if (!cancelled) setFactorId(factor?.id ?? null);
      if (!factor) router.replace(next);
    })();
    return () => {
      cancelled = true;
    };
  }, [supabase, router, next]);

  async function verify(event: React.FormEvent) {
    event.preventDefault();
    if (!factorId) return;
    setBusy(true);
    setError(null);
    const { data: challenge, error: challengeError } = await supabase.auth.mfa.challenge({ factorId });
    if (challengeError || !challenge) {
      setBusy(false);
      setError(challengeError?.message ?? t("auth.errors.generic"));
      return;
    }
    const { error: verifyError } = await supabase.auth.mfa.verify({
      factorId,
      challengeId: challenge.id,
      code: code.replace(/\s+/g, ""),
    });
    setBusy(false);
    if (verifyError) {
      setError(t("auth.mfa.invalidCode"));
      setCode("");
      return;
    }
    router.replace(next);
    router.refresh();
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">{t("auth.mfa.challengeTitle")}</h1>
      <p className="mt-1 text-sm text-text-muted">{t("auth.mfa.challengeHint")}</p>
      <form onSubmit={verify} className="mt-6 flex flex-col gap-4" noValidate>
        <Field label={t("auth.mfa.code")} htmlFor="code" error={error}>
          <Input
            id="code"
            inputMode="numeric"
            autoComplete="one-time-code"
            pattern="[0-9 ]*"
            maxLength={7}
            required
            autoFocus
            className="font-mono text-base tracking-[0.3em]"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            aria-invalid={error ? true : undefined}
          />
        </Field>
        <Button type="submit" loading={busy} disabled={!factorId || code.replace(/\s+/g, "").length < 6} className="w-full">
          {t("auth.mfa.verify")}
        </Button>
      </form>
      <form action="/auth/signout" method="post" className="mt-6 text-center">
        <Button type="submit" variant="link" className="text-xs text-text-muted">
          {t("auth.signOut")}
        </Button>
      </form>
    </div>
  );
}
