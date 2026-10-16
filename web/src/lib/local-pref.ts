"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * A small per-browser preference stored in localStorage (sidebar collapsed,
 * active workspace). Reads are hydration-safe: the server snapshot is the
 * default, and the browser value takes over after mount. Storage can be
 * unavailable (private windows, blocked site data), so every access is guarded.
 */
const listeners = new Set<() => void>();

function emit() {
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // ignore: preference simply does not persist
  }
  emit();
}

export function useLocalPref(key: string, fallback: string): [string, (value: string) => void] {
  const value = useSyncExternalStore(
    subscribe,
    () => readPref(key) ?? fallback,
    () => fallback,
  );
  const set = useCallback((next: string) => writePref(key, next), [key]);
  return [value, set];
}

/** True after hydration; false during server render and the first client render. */
export function useMounted(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
}
