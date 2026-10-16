"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox, Field, Input } from "@/components/ui/input";
import { t } from "@/lib/i18n";
import { PRIVACY_VERSION, TERMS_VERSION } from "@/lib/legal-versions";
import { createClient } from "@/lib/supabase/client";

const MIN_PASSWORD = 10;

export function SignupForm() {
  const router = useRouter();
  const supabase = createClient();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [accepted, setAccepted] = useState(false);
  const [acceptError, setAcceptError] = useState<string | null>(null);

  // Validated live: the message appears once the field has been used and
  // disappears the moment the password is long enough.
  const passwordTooShort = password.length < MIN_PASSWORD;
  const passwordError = passwordTouched && passwordTooShort ? t("auth.passwordHint") : null;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (passwordTooShort) {
      setPasswordTouched(true);
      return;
    }
    if (!accepted) {
      setAcceptError(t("auth.acceptTermsRequired"));
      return;
    }
    setBusy(true);
    const { data, error: signUpError } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: {
          full_name: fullName.trim(),
          locale: "en",
          accepted_terms_version: TERMS_VERSION,
          accepted_privacy_version: PRIVACY_VERSION,
          accepted_at: new Date().toISOString(),
        },
        emailRedirectTo: `${window.location.origin}/auth/callback?next=/library`,
      },
    });
    setBusy(false);
    if (signUpError) {
      setError(signUpError.message);
      return;
    }
    // With email confirmation on, no session is returned until the link is clicked.
    if (data.session) {
      router.replace("/library");
      router.refresh();
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{t("auth.signUpTitle")}</h1>
        <p className="mt-6 rounded-panel border border-border bg-surface p-4 text-sm" role="status">
          {t("auth.signUpSent")}
        </p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">{t("auth.signUpTitle")}</h1>
      <p className="mt-1 text-sm text-text-muted">{t("app.tagline")}</p>

      <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
        <Field label={t("auth.fullName")} htmlFor="full-name">
          <Input
            id="full-name"
            autoComplete="name"
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        </Field>
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
        <Field
          label={t("auth.password")}
          htmlFor="password"
          hint={`${t("auth.passwordHint")} ${password.length}/${MIN_PASSWORD}`}
          error={passwordError ?? error}
        >
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={MIN_PASSWORD}
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              setError(null);
            }}
            onBlur={() => setPasswordTouched(true)}
            aria-invalid={passwordError || error ? true : undefined}
          />
        </Field>
        <label className="flex items-start gap-2 text-sm">
          <Checkbox
            checked={accepted}
            onChange={(e) => {
              setAccepted(e.target.checked);
              if (e.target.checked) setAcceptError(null);
            }}
            aria-invalid={acceptError ? true : undefined}
          />
          <span>
            <ConsentSentence />
          </span>
        </label>
        {acceptError ? (
          <p className="-mt-2 text-xs text-danger" role="alert">
            {acceptError}
          </p>
        ) : null}
        <Button type="submit" loading={busy} className="mt-2 w-full">
          {t("auth.signUp")}
        </Button>
      </form>

      <p className="mt-8 text-center text-sm text-text-muted">
        {t("auth.haveAccount")}{" "}
        <Link href="/login" className="text-accent hover:underline">
          {t("auth.signIn")}
        </Link>
      </p>
    </div>
  );
}

/** "I have read and agree to the {terms} and the {privacy}." with links. */
function ConsentSentence() {
  const parts = t("auth.acceptTerms").split(/(\{terms\}|\{privacy\})/);
  return (
    <>
      {parts.map((part, i) => {
        if (part === "{terms}")
          return (
            <Link key={i} href="/legal/terms" target="_blank" className="text-accent hover:underline">
              {t("legal.terms")}
            </Link>
          );
        if (part === "{privacy}")
          return (
            <Link key={i} href="/legal/privacy" target="_blank" className="text-accent hover:underline">
              {t("legal.privacy")}
            </Link>
          );
        return <span key={i}>{part}</span>;
      })}
    </>
  );
}
