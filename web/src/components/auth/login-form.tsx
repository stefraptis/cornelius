"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/primitives";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

function safeNext(value: string | null): string {
  // Only allow same-origin paths to avoid open redirects.
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/library";
  return value;
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const supabase = createClient();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [linkSent, setLinkSent] = useState(false);

  async function signInWithPassword(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
    if (signInError) {
      setBusy(false);
      setError(
        signInError.message.toLowerCase().includes("invalid")
          ? t("auth.errors.invalidCredentials")
          : signInError.message,
      );
      return;
    }
    const { data: aal } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
    if (aal?.nextLevel === "aal2" && aal.currentLevel !== "aal2") {
      router.replace(`/mfa?next=${encodeURIComponent(next)}`);
      return;
    }
    router.replace(next);
    router.refresh();
  }

  async function sendMagicLink(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { error: otpError } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`,
      },
    });
    setBusy(false);
    if (otpError) {
      setError(otpError.message);
      return;
    }
    setLinkSent(true);
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">{t("auth.signInTitle")}</h1>
      <p className="mt-1 text-sm text-text-muted">{t("app.tagline")}</p>

      <Tabs defaultValue="password" className="mt-6">
        <TabsList>
          <TabsTrigger value="password">{t("auth.withPassword")}</TabsTrigger>
          <TabsTrigger value="magic">{t("auth.withMagicLink")}</TabsTrigger>
        </TabsList>

        <TabsContent value="password">
          <form onSubmit={signInWithPassword} className="flex flex-col gap-4" noValidate>
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
            <Field label={t("auth.password")} htmlFor="password" error={error}>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={error ? true : undefined}
              />
            </Field>
            <Button type="submit" loading={busy} className="mt-2 w-full">
              {t("auth.signIn")}
            </Button>
            <Link href="/reset-password" className="text-center text-xs text-text-muted hover:text-text">
              {t("auth.forgotPassword")}
            </Link>
          </form>
        </TabsContent>

        <TabsContent value="magic">
          {linkSent ? (
            <p className="rounded-panel border border-border bg-surface p-4 text-sm" role="status">
              {t("auth.magicLinkSent")}
            </p>
          ) : (
            <form onSubmit={sendMagicLink} className="flex flex-col gap-4" noValidate>
              <Field label={t("auth.email")} htmlFor="email-magic" error={error}>
                <Input
                  id="email-magic"
                  type="email"
                  autoComplete="email"
                  required
                  placeholder={t("auth.emailPlaceholder")}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </Field>
              <Button type="submit" loading={busy} className="mt-2 w-full">
                {t("auth.sendMagicLink")}
              </Button>
            </form>
          )}
        </TabsContent>
      </Tabs>

      <p className="mt-8 text-center text-sm text-text-muted">
        {t("auth.noAccount")}{" "}
        <Link href="/signup" className="text-accent hover:underline">
          {t("auth.signUp")}
        </Link>
      </p>
    </div>
  );
}
