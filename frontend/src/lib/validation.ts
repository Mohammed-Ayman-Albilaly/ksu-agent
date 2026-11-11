export const KSU_EMAIL_PATTERN = /^[^\s@]+@student\.ksu\.edu\.sa$/;

export type FieldErrorKey =
  | "nameRequired"
  | "nameLength"
  | "emailRequired"
  | "emailDomain"
  | "passwordRequired"
  | "passwordLength"
  | "passwordWeak"
  | "confirmRequired"
  | "confirmMismatch"
  | "agreeRequired";

export function normalizeEmail(value: string): string {
  return value.trim().toLowerCase();
}

export function validateFullName(value: string): FieldErrorKey | null {
  const name = value.trim();

  if (!name) {
    return "nameRequired";
  }

  if (name.length < 2 || name.length > 60) {
    return "nameLength";
  }

  return null;
}

export function validateEmail(value: string): FieldErrorKey | null {
  const email = normalizeEmail(value);

  if (!email) {
    return "emailRequired";
  }

  if (!KSU_EMAIL_PATTERN.test(email)) {
    return "emailDomain";
  }

  return null;
}

export function validateNewPassword(value: string): FieldErrorKey | null {
  if (!value) {
    return "passwordRequired";
  }

  if (value.length < 8) {
    return "passwordLength";
  }

  if (!/[A-Za-z\u0600-\u06FF]/.test(value) || !/[0-9]/.test(value)) {
    return "passwordWeak";
  }

  return null;
}

export function validateConfirm(
  password: string,
  confirm: string,
): FieldErrorKey | null {
  if (!confirm) {
    return "confirmRequired";
  }

  if (confirm !== password) {
    return "confirmMismatch";
  }

  return null;
}

export function resolveNextPath(): string {
  if (typeof window === "undefined") {
    return "/chat";
  }

  const value = new URLSearchParams(window.location.search).get("next");

  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/chat";
  }

  if (value.startsWith("/\\")) {
    return "/chat";
  }

  return value;
}
