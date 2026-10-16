import type { Metadata } from "next";

import { SignupForm } from "@/components/auth/signup-form";
import { t } from "@/lib/i18n";

export const metadata: Metadata = { title: t("auth.signUpTitle") };

export default function SignupPage() {
  return <SignupForm />;
}
