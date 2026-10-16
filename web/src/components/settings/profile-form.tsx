"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, Input, Select } from "@/components/ui/input";
import { api, type Profile } from "@/lib/api";
import { locales, t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

export function ProfileForm({ profile, email }: { profile: Profile; email: string | null }) {
  const router = useRouter();
  const supabase = createClient();
  const [fullName, setFullName] = useState(profile.full_name);
  const [title, setTitle] = useState(profile.title ?? "");
  const [specialty, setSpecialty] = useState(profile.specialty ?? "");
  const [locale, setLocale] = useState(profile.locale);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session) {
      router.replace("/login");
      return;
    }
    try {
      await api.updateProfile(session.access_token, {
        full_name: fullName.trim(),
        title: title.trim() || null,
        specialty: specialty.trim() || null,
        locale,
      });
      toast.success(t("settings.profileSaved"));
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("auth.errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <Field label={t("settings.accountEmail")} htmlFor="account-email">
        <Input id="account-email" value={email ?? ""} readOnly disabled />
      </Field>
      <Field label={t("auth.fullName")} htmlFor="full-name">
        <Input id="full-name" value={fullName} onChange={(e) => setFullName(e.target.value)} required />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("settings.title_field")} htmlFor="title">
          <Input id="title" value={title} placeholder={t("settings.titlePlaceholder")} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label={t("settings.specialty")} htmlFor="specialty">
          <Input
            id="specialty"
            value={specialty}
            placeholder={t("settings.specialtyPlaceholder")}
            onChange={(e) => setSpecialty(e.target.value)}
          />
        </Field>
      </div>
      <Field label={t("settings.locale")} htmlFor="locale">
        <Select id="locale" value={locale} onChange={(e) => setLocale(e.target.value)}>
          {locales.map((code) => (
            <option key={code} value={code}>
              {code === "en" ? "English" : code}
            </option>
          ))}
        </Select>
      </Field>
      <div>
        <Button type="submit" loading={busy}>
          {t("settings.save")}
        </Button>
      </div>
    </form>
  );
}
