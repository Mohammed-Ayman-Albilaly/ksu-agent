"use client";

import { useState, type Ref } from "react";
import { FormField } from "@/components/auth/FormField";
import { useLanguage } from "@/components/LanguageProvider";
import { EyeIcon, EyeOffIcon } from "@/components/icons";

type PasswordFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  error?: string;
  autoComplete: "current-password" | "new-password";
  inputRef?: Ref<HTMLInputElement>;
};

export function PasswordField({
  id,
  label,
  value,
  onChange,
  onBlur,
  error,
  autoComplete,
  inputRef,
}: PasswordFieldProps) {
  const { t } = useLanguage();
  const [visible, setVisible] = useState(false);

  return (
    <FormField
      id={id}
      label={label}
      value={value}
      onChange={onChange}
      onBlur={onBlur}
      error={error}
      type={visible ? "text" : "password"}
      autoComplete={autoComplete}
      dir="ltr"
      inputRef={inputRef}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          aria-label={
            visible ? t.auth.fields.hidePassword : t.auth.fields.showPassword
          }
          aria-pressed={visible}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface hover:text-navy"
        >
          {visible ? (
            <EyeOffIcon className="h-4 w-4" />
          ) : (
            <EyeIcon className="h-4 w-4" />
          )}
        </button>
      }
    />
  );
}
