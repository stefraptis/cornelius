import { type EmailOtpType } from "@supabase/supabase-js";
import { NextResponse, type NextRequest } from "next/server";

import { createClient } from "@/lib/supabase/server";

function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/library";
  return value;
}

/**
 * Lands magic links, sign-up confirmations, and password recovery links.
 * Supports both the PKCE flow (?code=) and token-hash links (?token_hash=&type=).
 */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const tokenHash = searchParams.get("token_hash");
  const type = searchParams.get("type") as EmailOtpType | null;
  const next = safeNext(searchParams.get("next"));

  const supabase = await createClient();
  let failed = false;

  if (code) {
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    failed = Boolean(error);
  } else if (tokenHash && type) {
    const { error } = await supabase.auth.verifyOtp({ token_hash: tokenHash, type });
    failed = Boolean(error);
  } else {
    failed = true;
  }

  if (failed) {
    return NextResponse.redirect(`${origin}/login?error=invalid_link`);
  }
  if (type === "recovery") {
    return NextResponse.redirect(`${origin}/reset-password/update`);
  }
  return NextResponse.redirect(`${origin}${next}`);
}
