"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent } from "react";
import { useAuth } from "@/components/AuthProvider";
import { useLanguage } from "@/components/LanguageProvider";
import { AuthCard } from "@/components/auth/AuthCard";
import { FormField } from "@/components/auth/FormField";
import { PasswordField } from "@/components/auth/PasswordField";
import { SubmitButton } from "@/components/auth/SubmitButton";
import { useRedirectIfAuthenticated } from "@/components/auth/useRedirectIfAuthenticated";
import {
  normalizeEmail,
  resolveNextPath,
  validateEmail,
  type FieldErrorKey,
} from "@/lib/validation";

type FieldName = "email" | "password";

const FIELD_ORDER: FieldName[] = ["email", "password"];

type Values = {
  email: string;
  password: string;
};

export function LoginForm() {
  const { t } = useLanguage();
  const { login } = useAuth();
  const router = useRouter();
  const { markLeaving } = useRedirectIfAuthenticated();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorKeys, setErrorKeys] = useState<
    Partial<Record<FieldName, FieldErrorKey>>
  >({});
  const [serverErrors, setServerErrors] = useState<
    Partial<Record<FieldName, string>>
  >({});
  const [formError, setFormError] = useState<string | null>(null);
  const [touched, setTouched] = useState<Partial<Record<FieldName, boolean>>>(
    {},
  );
  const [pending, setPending] = useState(false);

  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const fieldRefs = { email: emailRef, password: passwordRef };

  const collectErrors = (values: Values) => {
    const next: Partial<Record<FieldName, FieldErrorKey>> = {};
    const emailError = validateEmail(values.email);

    if (emailError) {
      next.email = emailError;
    }

    if (!values.password) {
      next.password = "passwordRequired";
    }

    return next;
  };

  const validateField = (field: FieldName) => {
    const next = collectErrors({ email, password })[field];

    setErrorKeys((current) => ({ ...current, [field]: next }));
    setServerErrors((current) => ({ ...current, [field]: undefined }));
  };

  const fieldError = (field: FieldName) => {
    const serverError = serverErrors[field];

    if (serverError) {
      return serverError;
    }

    const key = errorKeys[field];

    return key ? t.auth.errors[key] : undefined;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (pending) {
      return;
    }

    const nextErrors = collectErrors({ email, password });

    setTouched({ email: true, password: true });
    setErrorKeys(nextErrors);
    setServerErrors({});
    setFormError(null);

    const firstInvalid = FIELD_ORDER.find((field) => nextErrors[field]);

    if (firstInvalid) {
      fieldRefs[firstInvalid].current?.focus();
      return;
    }

    setPending(true);

    const result = await login({
      email: normalizeEmail(email),
      password,
    });

    if (result.ok) {
      markLeaving();
      router.replace(resolveNextPath());
      return;
    }

    setPending(false);

    if (result.error === "validation") {
      const fields = result.fields ?? {};
      const mapped: Partial<Record<FieldName, string>> = {};

      if (fields.email) {
        mapped.email = fields.email;
      }

      if (fields.password) {
        mapped.password = fields.password;
      }

      setServerErrors(mapped);
      setFormError(t.auth.server.validation);

      const firstField = FIELD_ORDER.find((field) => mapped[field]);

      if (firstField) {
        fieldRefs[firstField].current?.focus();
      }

      return;
    }

    setFormError(
      result.error === "invalid_credentials"
        ? t.auth.server.invalidCredentials
        : t.auth.server.serverUnavailable,
    );
  };

  return (
    <AuthCard
      title={t.auth.login.title}
      subtitle={t.auth.login.subtitle}
      switchText={t.auth.login.switchText}
      switchLink={t.auth.login.switchLink}
      switchHref="/register"
    >
      <form noValidate onSubmit={handleSubmit}>
        {formError ? (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          >
            {formError}
          </div>
        ) : null}

        <div className="space-y-4">
          <FormField
            id="login-email"
            label={t.auth.fields.email}
            value={email}
            onChange={(value) => {
              setEmail(value);

              if (touched.email) {
                setErrorKeys((current) => ({
                  ...current,
                  email: validateEmail(value) ?? undefined,
                }));
              }
            }}
            onBlur={() => {
              setTouched((current) => ({ ...current, email: true }));
              validateField("email");
            }}
            error={fieldError("email")}
            type="email"
            inputMode="email"
            autoComplete="email"
            dir="ltr"
            inputRef={emailRef}
          />

          <PasswordField
            id="login-password"
            label={t.auth.fields.password}
            value={password}
            onChange={(value) => {
              setPassword(value);

              if (touched.password) {
                setErrorKeys((current) => ({
                  ...current,
                  password: value ? undefined : "passwordRequired",
                }));
              }
            }}
            onBlur={() => {
              setTouched((current) => ({ ...current, password: true }));
              validateField("password");
            }}
            error={fieldError("password")}
            autoComplete="current-password"
            inputRef={passwordRef}
          />
        </div>

        <SubmitButton label={t.auth.login.submit} pending={pending} />
      </form>
    </AuthCard>
  );
}
