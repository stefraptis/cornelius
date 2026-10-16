"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/input";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";

export default function UpdatePasswordPage() {
  const router = useRouter();
  const supabase = createClient();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (password.length < 10) {
      setError(t("auth.passwordHint"));
      return;
    }
    setBusy(true);
    const { error: updateError } = await supabase.auth.updateUser({ password });
    setBusy(false);
    if (updateError) {
      setError(updateError.message);
      return;
    }
    toast.success(t("auth.passwordUpdated"));
    router.replace("/library");
    router.refresh();
  }

  return (
    <div>
      <h1 className="text-xl font-semibold tracking-tight">{t("auth.updatePassword")}</h1>
      <form onSubmit={submit} className="mt-6 flex flex-col gap-4" noValidate>
        <Field label={t("auth.newPassword")} htmlFor="password" hint={t("auth.passwordHint")} error={error}>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <Button type="submit" loading={busy} className="mt-2 w-full">
          {t("auth.updatePassword")}
        </Button>
      </form>
    </div>
  );
}
