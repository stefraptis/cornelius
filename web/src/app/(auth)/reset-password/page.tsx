"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

export default function ResetPasswordPage() {
  const supabase = createClient();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/callback?type=recovery`,
    });
    // Always report success so the form does not reveal which emails exist.
    setBusy(false);
    setSent(true);
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">{t("auth.resetPassword")}</h1>
      {sent ? (
        <p className="mt-6 rounded-panel border border-border bg-surface p-4 text-sm" role="status">
          {t("auth.resetSent")}
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
          <Field label={t("auth.email")} htmlFor="email">
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              placeholder={t("auth.emailPlaceholder")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </Field>
          <Button type="submit" loading={busy} className="mt-2 w-full">
            {t("auth.resetPassword")}
          </Button>
        </form>
      )}
      <p className="mt-8 text-center text-sm text-text-muted">
        <Link href="/login" className="text-accent hover:underline">
          {t("common.back")}
        </Link>
      </p>
    </div>
  );
}
