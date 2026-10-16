"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Panel, PanelHeader } from "@/components/ui/display";
import { Field, Input } from "@/components/ui/input";
import { type Consent, privacyApi } from "@/lib/api";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

export function PrivacySettings({ email, consent }: { email: string | null; consent: Consent }) {
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState<"export" | "delete" | null>(null);

  async function token(): Promise<string | null> {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    return session?.access_token ?? null;
  }

  async function download() {
    setBusy("export");
    try {
      const access = await token();
      if (!access) return router.replace("/login");
      const response = await fetch(privacyApi.exportUrl(), { headers: { Authorization: `Bearer ${access}` } });
      if (!response.ok) throw new Error(response.statusText);
      const blob = await response.blob();
      const name = response.headers.get("content-disposition")?.match(/filename="([^"]+)"/)?.[1] ?? "export.json";
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
    } finally {
      setBusy(null);
    }
  }

  async function deleteAccount(event: React.FormEvent) {
    event.preventDefault();
    if (!email || confirm.trim().toLowerCase() !== email.toLowerCase()) return;
    setBusy("delete");
    try {
      const access = await token();
      if (!access) return router.replace("/login");
      await privacyApi.deleteAccount(access, confirm.trim());
      await createClient().auth.signOut();
      toast.success(t("settings.deleteDone"));
      router.replace("/login");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
      setBusy(null);
    }
  }

  const canDelete = Boolean(email) && confirm.trim().toLowerCase() === (email ?? "").toLowerCase();

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm text-text-muted">{t("settings.privacyIntro")}</p>

      <Panel>
        <PanelHeader title={t("settings.consentTitle")} />
        <div className="p-5 text-sm">
          {consent.accepted_at ? (
            <p>
              {t("settings.consentBody", {
                terms: consent.terms_version ?? "",
                privacy: consent.privacy_version ?? "",
                date: new Date(consent.accepted_at).toLocaleDateString(),
              })}
            </p>
          ) : (
            <p className="text-text-muted">{t("settings.consentNone")}</p>
          )}
          <p className="mt-2 flex flex-wrap gap-3 text-xs">
            {(["terms", "privacy", "cookies", "subprocessors"] as const).map((k) => (
              <Link key={k} href={`/legal/${k}`} target="_blank" className="text-accent hover:underline">
                {t(`legal.${k}`)}
              </Link>
            ))}
          </p>
        </div>
      </Panel>

      <Panel>
        <PanelHeader title={t("settings.exportTitle")} description={t("settings.exportBody")} />
        <div className="p-5">
          <Button variant="secondary" onClick={download} loading={busy === "export"}>
            {t("settings.exportButton")}
          </Button>
        </div>
      </Panel>

      <Panel className="border-danger/40">
        <PanelHeader title={t("settings.deleteTitle")} description={t("settings.deleteBody")} />
        <form onSubmit={deleteAccount} className="flex flex-col gap-4 p-5">
          <Field label={t("settings.deleteConfirmLabel")} htmlFor="delete-confirm" className="max-w-sm">
            <Input
              id="delete-confirm"
              type="email"
              autoComplete="off"
              placeholder={email ?? ""}
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </Field>
          <div>
            <Button type="submit" variant="danger" disabled={!canDelete} loading={busy === "delete"}>
              {t("settings.deleteButton")}
            </Button>
          </div>
        </form>
      </Panel>
    </div>
  );
}
