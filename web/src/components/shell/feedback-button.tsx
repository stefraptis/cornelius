"use client";

import { MessageSquare } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/primitives";
import { APP_VERSION, api, type FeedbackCategory } from "@/lib/api";
import { t } from "@/lib/i18n";
import { createClient } from "@/lib/supabase/client";
import { track } from "@/lib/usage";
import { cn } from "@/lib/utils";

const CATEGORIES: FeedbackCategory[] = ["bug", "idea", "question", "other"];

export function FeedbackButton({ compact = false }: { compact?: boolean }) {
  const [open, setOpen] = useState(false);
  const [category, setCategory] = useState<FeedbackCategory>("other");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!message.trim()) return;
    setBusy(true);
    try {
      const {
        data: { session },
      } = await createClient().auth.getSession();
      if (!session) throw new Error("no session");
      await api.sendFeedback(session.access_token, {
        category,
        message: message.trim(),
        page_url: window.location.pathname + window.location.search,
        app_version: APP_VERSION,
      });
      track("feedback.sent", { category });
      toast.success(t("feedback.sent"));
      setMessage("");
      setCategory("other");
      setOpen(false);
    } catch {
      toast.error(t("feedback.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size={compact ? "icon" : "sm"} aria-label={t("feedback.button")}>
          <MessageSquare aria-hidden />
          {!compact ? t("feedback.button") : null}
        </Button>
      </DialogTrigger>
      <DialogContent title={t("feedback.title")} description={t("feedback.description")}>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <Field label={t("feedback.category")} htmlFor="feedback-category">
            <Select
              id="feedback-category"
              value={category}
              onChange={(e) => setCategory(e.target.value as FeedbackCategory)}
            >
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`feedback.categories.${c}`)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("feedback.message")} htmlFor="feedback-message">
            <textarea
              id="feedback-message"
              required
              rows={5}
              maxLength={4000}
              placeholder={t("feedback.messagePlaceholder")}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              className={cn(
                "w-full rounded-control border border-border bg-bg px-3 py-2 text-sm text-text placeholder:text-text-muted",
                "focus-visible:border-accent",
              )}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={busy} disabled={!message.trim()}>
              {t("feedback.send")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
