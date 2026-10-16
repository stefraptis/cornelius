"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { installFlushOnHide, track } from "@/lib/usage";

/** Records a page.view per route change, with the time spent on the previous page. */
export function UsageTracker() {
  const pathname = usePathname();
  const enteredAt = useRef<number>(0);
  const previous = useRef<string | null>(null);

  useEffect(() => installFlushOnHide(), []);

  useEffect(() => {
    const now = Date.now();
    if (previous.current && previous.current !== pathname) {
      track("page.leave", { path: previous.current }, now - enteredAt.current);
    }
    enteredAt.current = now;
    previous.current = pathname;
    track("page.view", { path: pathname });
  }, [pathname]);

  return null;
}
