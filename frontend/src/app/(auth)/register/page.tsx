import type { Metadata } from "next";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { dictionary } from "@/lib/i18n";

export const metadata: Metadata = {
  title: dictionary.ar.auth.register.metaTitle,
};

export default function RegisterPage() {
  return <RegisterForm />;
}
