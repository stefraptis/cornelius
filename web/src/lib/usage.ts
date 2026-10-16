"use client";

/**
 * Usage tracking: first-party, batched, EU only.
 *
 * `track(event, properties)` queues an event; the queue is flushed every few
 * seconds, when it reaches 20 events, and when the tab is hidden or closed.
 * Page views are recorded by <UsageTracker/> in the app shell. Properties
 * must be small scalars; never put patient data or free text in them.
 */
import { api, type UsageEvent } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";

const FLUSH_MS = 5000;
const MAX_BATCH = 20;

let queue: UsageEvent[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let sessionId: string | null = null;

function getSessionId(): string {
  if (sessionId) return sessionId;
  try {
    const existing = window.sessionStorage.getItem("cornelius.session");
    if (existing) return (sessionId = existing);
    const fresh = Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    window.sessionStorage.setItem("cornelius.session", fresh);
    return (sessionId = fresh);
  } catch {
    return (sessionId = "s" + Date.now().toString(36));
  }
}

export function track(
  event: string,
  properties?: Record<string, string | number | boolean | null>,
  durationMs?: number,
) {
  if (typeof window === "undefined") return;
  queue.push({
    event,
    page: window.location.pathname,
    properties,
    duration_ms: durationMs,
    session_id: getSessionId(),
    at: new Date().toISOString(),
  });
  if (queue.length >= MAX_BATCH) {
    void flush();
  } else if (!timer) {
    timer = setTimeout(() => void flush(), FLUSH_MS);
  }
}

export async function flush(): Promise<void> {
  if (timer) {
    clearTimeout(timer);
    timer = null;
  }
  if (queue.length === 0) return;
  const batch = queue;
  queue = [];
  try {
    const {
      data: { session },
    } = await createClient().auth.getSession();
    if (!session) return;
    await api.sendUsage(session.access_token, batch);
  } catch {
    // Usage is best effort. Keep the batch for the next flush, bounded.
    queue = batch.concat(queue).slice(-100);
  }
}

/** Called once from the tracker component. */
export function installFlushOnHide(): () => void {
  const onVisibility = () => {
    if (document.visibilityState === "hidden") void flush();
  };
  document.addEventListener("visibilitychange", onVisibility);
  window.addEventListener("pagehide", onVisibility);
  return () => {
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("pagehide", onVisibility);
  };
}
