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
  validateConfirm,
  validateEmail,
  validateFullName,
  validateNewPassword,
  type FieldErrorKey,
} from "@/lib/validation";

type FieldName = "name" | "email" | "password" | "confirm" | "agree";

const FIELD_ORDER: FieldName[] = [
  "name",
  "email",
  "password",
  "confirm",
  "agree",
];

type Values = {
  name: string;
  email: string;
  password: string;
  confirm: string;
  agree: boolean;
};

const SERVER_FIELDS: Record<string, FieldName> = {
  full_name: "name",
  email: "email",
  password: "password",
};

export function RegisterForm() {
  const { t, lang } = useLanguage();
  const { register } = useAuth();
  const router = useRouter();
  const { markLeaving } = useRedirectIfAuthenticated();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agree, setAgree] = useState(false);
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

  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const agreeRef = useRef<HTMLInputElement>(null);
  const fieldRefs = {
    name: nameRef,
    email: emailRef,
    password: passwordRef,
    confirm: confirmRef,
    agree: agreeRef,
  };

  const collectErrors = (values: Values) => {
    const next: Partial<Record<FieldName, FieldErrorKey>> = {};
    const nameError = validateFullName(values.name);
    const emailError = validateEmail(values.email);
    const passwordError = validateNewPassword(values.password);
    const confirmError = validateConfirm(values.password, values.confirm);

    if (nameError) {
      next.name = nameError;
    }

    if (emailError) {
      next.email = emailError;
    }

    if (passwordError) {
      next.password = passwordError;
    }

    if (confirmError) {
      next.confirm = confirmError;
    }

    if (!values.agree) {
      next.agree = "agreeRequired";
    }

    return next;
  };

  const currentValues = (): Values => ({
    name,
    email,
    password,
    confirm,
    agree,
  });

  const validateField = (field: FieldName) => {
    const next = collectErrors(currentValues())[field];

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

  const touchField = (field: FieldName) => {
    setTouched((current) => ({ ...current, [field]: true }));
    validateField(field);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (pending) {
      return;
    }

    const nextErrors = collectErrors(currentValues());

    setTouched({
      name: true,
      email: true,
      password: true,
      confirm: true,
      agree: true,
    });
    setErrorKeys(nextErrors);
    setServerErrors({});
    setFormError(null);

    const firstInvalid = FIELD_ORDER.find((field) => nextErrors[field]);

    if (firstInvalid) {
      fieldRefs[firstInvalid].current?.focus();
      return;
    }

    setPending(true);

    const result = await register({
      fullName: name.trim(),
      email: normalizeEmail(email),
      password,
      lang,
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

      for (const [serverField, message] of Object.entries(fields)) {
        const field = SERVER_FIELDS[serverField];

        if (field) {
          mapped[field] = message;
        }
      }

      setServerErrors(mapped);
      setFormError(t.auth.server.validation);

      const firstField = FIELD_ORDER.find((field) => mapped[field]);

      if (firstField) {
        fieldRefs[firstField].current?.focus();
      }

      return;
    }

    if (result.error === "email_taken") {
      setFormError(t.auth.server.emailTaken);
      emailRef.current?.focus();
      return;
    }

    setFormError(t.auth.server.serverUnavailable);
  };

  return (
    <AuthCard
      title={t.auth.register.title}
      subtitle={t.auth.register.subtitle}
      switchText={t.auth.register.switchText}
      switchLink={t.auth.register.switchLink}
      switchHref="/login"
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
            id="register-name"
            label={t.auth.fields.name}
            value={name}
            onChange={(value) => {
              setName(value);

              if (touched.name) {
                setErrorKeys((current) => ({
                  ...current,
                  name: validateFullName(value) ?? undefined,
                }));
              }
            }}
            onBlur={() => touchField("name")}
            error={fieldError("name")}
            autoComplete="name"
            inputRef={nameRef}
          />

          <FormField
            id="register-email"
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
            onBlur={() => touchField("email")}
            error={fieldError("email")}
            hint={t.auth.fields.emailHint}
            type="email"
            inputMode="email"
            autoComplete="email"
            dir="ltr"
            inputRef={emailRef}
          />

          <PasswordField
            id="register-password"
            label={t.auth.fields.password}
            value={password}
            onChange={(value) => {
              setPassword(value);

              if (touched.password) {
                setErrorKeys((current) => ({
                  ...current,
                  password: validateNewPassword(value) ?? undefined,
                }));
              }

              if (touched.confirm && confirm) {
                setErrorKeys((current) => ({
                  ...current,
                  confirm: validateConfirm(value, confirm) ?? undefined,
                }));
              }
            }}
            onBlur={() => touchField("password")}
            error={fieldError("password")}
            autoComplete="new-password"
            inputRef={passwordRef}
          />

          <PasswordField
            id="register-confirm"
            label={t.auth.fields.confirm}
            value={confirm}
            onChange={(value) => {
              setConfirm(value);

              if (touched.confirm) {
                setErrorKeys((current) => ({
                  ...current,
                  confirm: validateConfirm(password, value) ?? undefined,
                }));
              }
            }}
            onBlur={() => touchField("confirm")}
            error={fieldError("confirm")}
            autoComplete="new-password"
            inputRef={confirmRef}
          />

          <div>
            <div className="flex items-start gap-2.5">
              <input
                id="register-agree"
                ref={agreeRef}
                type="checkbox"
                checked={agree}
                onChange={(event) => {
                  setAgree(event.target.checked);

                  if (touched.agree) {
                    setErrorKeys((current) => ({
                      ...current,
                      agree: event.target.checked ? undefined : "agreeRequired",
                    }));
                  }
                }}
                onBlur={() => touchField("agree")}
                aria-invalid={fieldError("agree") ? true : undefined}
                aria-describedby={
                  fieldError("agree") ? "register-agree-error" : undefined
                }
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-slate-300 accent-teal-deep"
              />
              <label
                htmlFor="register-agree"
                className="text-sm leading-relaxed text-ink"
              >
                {t.auth.fields.agree}
              </label>
            </div>

            {fieldError("agree") ? (
              <p
                id="register-agree-error"
                className="mt-1.5 text-xs font-medium text-red-600"
              >
                {fieldError("agree")}
              </p>
            ) : null}
          </div>
        </div>

        <SubmitButton label={t.auth.register.submit} pending={pending} />
      </form>
    </AuthCard>
  );
}
