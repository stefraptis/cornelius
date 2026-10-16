/**
 * Public environment, readable in the browser. Only NEXT_PUBLIC_* values
 * belong here; the frontend never holds storage or service-role keys.
 */
function required(name: string, value: string | undefined, fallback?: string): string {
  if (value && value.length > 0) return value;
  if (fallback !== undefined) return fallback;
  throw new Error(`Missing environment variable ${name}. Copy .env.example to .env and fill it in.`);
}

export const env = {
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "Cornelius",
  supabaseUrl: required(
    "NEXT_PUBLIC_SUPABASE_URL",
    process.env.NEXT_PUBLIC_SUPABASE_URL,
    "http://localhost:54321",
  ),
  supabaseAnonKey: required(
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    "anon-key-not-set",
  ),
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
};
