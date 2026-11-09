import type { Metadata } from "next";
import { LoginForm } from "@/components/auth/LoginForm";
import { dictionary } from "@/lib/i18n";

export const metadata: Metadata = {
  title: dictionary.ar.auth.login.metaTitle,
};

export default function LoginPage() {
  return <LoginForm />;
}
