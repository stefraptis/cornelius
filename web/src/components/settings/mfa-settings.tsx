"use client";

/* eslint-disable @next/next/no-img-element */
import { ShieldCheck, ShieldOff } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Chip, Skeleton } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/input";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

type Factor = { id: string; friendly_name?: string; status: "verified" | "unverified"; created_at: string };

type Enrollment = { factorId: string; qrCode: string; secret: string };

export function MfaSettings() {
  const router = useRouter();
  const supabase = createClient();
  const [factors, setFactors] = useState<Factor[] | null>(null);
  const [enrollment, setEnrollment] = useState<Enrollment | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFactors = useCallback(async (): Promise<Factor[]> => {
    const { data, error: listError } = await supabase.auth.mfa.listFactors();
    if (listError) {
      toast.error(listError.message);
      return [];
    }
    const totp = (data?.totp ?? []) as Factor[];
    // Clean up abandoned enrollments so the user does not accumulate them.
    for (const f of totp.filter((x) => x.status === "unverified")) {
      await supabase.auth.mfa.unenroll({ factorId: f.id });
    }
    return totp.filter((x) => x.status === "verified");
  }, [supabase]);

  const load = useCallback(() => fetchFactors().then(setFactors), [fetchFactors]);

  useEffect(() => {
    let cancelled = false;
    fetchFactors().then((result) => {
      if (!cancelled) setFactors(result);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchFactors]);

  async function startEnrollment() {
    setBusy(true);
    setError(null);
    const { data, error: enrollError } = await supabase.auth.mfa.enroll({
      factorType: "totp",
      friendlyName: t("auth.mfa.factorName"),
    });
    setBusy(false);
    if (enrollError || !data) {
      toast.error(enrollError?.message ?? t("auth.errors.generic"));
      return;
    }
    setEnrollment({ factorId: data.id, qrCode: data.totp.qr_code, secret: data.totp.secret });
  }

  async function confirmEnrollment(event: React.FormEvent) {
    event.preventDefault();
    if (!enrollment) return;
    setBusy(true);
    setError(null);
    const { data: challenge, error: challengeError } = await supabase.auth.mfa.challenge({
      factorId: enrollment.factorId,
    });
    if (challengeError || !challenge) {
      setBusy(false);
      setError(challengeError?.message ?? t("auth.errors.generic"));
      return;
    }
    const { error: verifyError } = await supabase.auth.mfa.verify({
      factorId: enrollment.factorId,
      challengeId: challenge.id,
      code: code.replace(/\s+/g, ""),
    });
    setBusy(false);
    if (verifyError) {
      setError(t("auth.mfa.invalidCode"));
      setCode("");
      return;
    }
    setEnrollment(null);
    setCode("");
    toast.success(t("auth.mfa.enrolled"));
    await load();
    router.refresh();
  }

  async function cancelEnrollment() {
    if (enrollment) await supabase.auth.mfa.unenroll({ factorId: enrollment.factorId });
    setEnrollment(null);
    setCode("");
    setError(null);
  }

  async function remove(factorId: string) {
    if (!window.confirm(t("auth.mfa.removeConfirm"))) return;
    setBusy(true);
    const { error: unenrollError } = await supabase.auth.mfa.unenroll({ factorId });
    setBusy(false);
    if (unenrollError) {
      toast.error(unenrollError.message);
      return;
    }
    toast.success(t("auth.mfa.removed"));
    await load();
    router.refresh();
  }

  if (factors === null) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-9 w-40" />
      </div>
    );
  }

  if (enrollment) {
    return (
      <form onSubmit={confirmEnrollment} className="flex flex-col gap-5" noValidate>
        <p className="text-sm text-text-muted">{t("auth.mfa.enrollHint")}</p>
        <div className="flex flex-wrap items-start gap-6">
          <div className="rounded-panel border border-border bg-white p-2">
            <img src={enrollment.qrCode} alt="" width={176} height={176} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-xs font-medium uppercase tracking-wide text-text-muted">{t("auth.mfa.secret")}</div>
            <code className="mt-1 block break-all rounded-control border border-border bg-surface px-2 py-1.5 font-mono text-xs">
              {enrollment.secret}
            </code>
          </div>
        </div>
        <Field label={t("auth.mfa.code")} htmlFor="totp-code" error={error} className="max-w-xs">
          <Input
            id="totp-code"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={7}
            required
            autoFocus
            className="font-mono text-base tracking-[0.3em]"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            aria-invalid={error ? true : undefined}
          />
        </Field>
        <div className="flex gap-2">
          <Button type="submit" loading={busy} disabled={code.replace(/\s+/g, "").length < 6}>
            {t("auth.mfa.verify")}
          </Button>
          <Button type="button" variant="ghost" onClick={cancelEnrollment} disabled={busy}>
            {t("common.cancel")}
          </Button>
        </div>
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {factors.length > 0 ? (
        <>
          <div className="flex items-center gap-2 text-sm">
            <ShieldCheck className="size-4 text-accent" aria-hidden />
            {t("auth.mfa.enrolled")}
          </div>
          <ul className="divide-y divide-border rounded-panel border border-border">
            {factors.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                <div className="flex items-center gap-3">
                  <span>{f.friendly_name || t("auth.mfa.factorName")}</span>
                  <Chip tone="accent">{f.status}</Chip>
                </div>
                <Button variant="ghost" size="sm" onClick={() => remove(f.id)} disabled={busy}>
                  {t("auth.mfa.remove")}
                </Button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <div className="flex items-start gap-2 text-sm text-text-muted">
            <ShieldOff className="mt-0.5 size-4 shrink-0" aria-hidden />
            {t("auth.mfa.notEnrolled")}
          </div>
          <div>
            <Button onClick={startEnrollment} loading={busy}>
              {t("auth.mfa.enroll")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
