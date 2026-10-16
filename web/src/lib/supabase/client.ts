"use client";

import { createBrowserClient } from "@supabase/ssr";

import { env } from "@/lib/env";

let client: ReturnType<typeof createBrowserClient> | undefined;

/** Browser-side Supabase client (anon key; RLS protects data). */
export function createClient() {
  if (!client) {
    client = createBrowserClient(env.supabaseUrl, env.supabaseAnonKey);
  }
  return client;
}
