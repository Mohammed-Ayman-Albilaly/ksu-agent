import type { Lang } from "@/lib/i18n";

export type AuthUser = {
  id: string;
  full_name: string;
  email: string;
};

export type AuthErrorCode =
  | "email_taken"
  | "invalid_credentials"
  | "validation"
  | "server_unavailable";

export type AuthResult =
  | { ok: true; user: AuthUser }
  | { ok: false; error: AuthErrorCode; fields?: Record<string, string> };

export type MeResult =
  | { ok: true; user: AuthUser }
  | { ok: false; error: "unauthenticated" | "server_unavailable" };

export type LogoutResult = { ok: true } | { ok: false; error: "server_unavailable" };

export type RegisterInput = {
  fullName: string;
  email: string;
  password: string;
  lang: Lang;
};

export type LoginInput = {
  email: string;
  password: string;
};

const MODE = process.env.NEXT_PUBLIC_AUTH_MODE === "api" ? "api" : "mock";
const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/+$/, "");

async function send(path: string, init: RequestInit): Promise<Response | null> {
  try {
    return await fetch(`${BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return null;
  }
}

async function readBody<T>(response: Response): Promise<T | null> {
  try {
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

async function loadMock() {
  return import("./authMock");
}

export async function register(input: RegisterInput): Promise<AuthResult> {
  if (MODE === "mock") {
    const { mockRegister } = await loadMock();
    return mockRegister(input);
  }

  const response = await send("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      full_name: input.fullName,
      email: input.email,
      password: input.password,
      lang: input.lang,
    }),
  });

  if (!response) {
    return { ok: false, error: "server_unavailable" };
  }

  if (response.status === 201) {
    const body = await readBody<{ user?: AuthUser }>(response);
    return body?.user
      ? { ok: true, user: body.user }
      : { ok: false, error: "server_unavailable" };
  }

  if (response.status === 409) {
    return { ok: false, error: "email_taken" };
  }

  if (response.status === 422) {
    const body = await readBody<{ fields?: Record<string, string> }>(response);
    return { ok: false, error: "validation", fields: body?.fields ?? {} };
  }

  return { ok: false, error: "server_unavailable" };
}

export async function login(input: LoginInput): Promise<AuthResult> {
  if (MODE === "mock") {
    const { mockLogin } = await loadMock();
    return mockLogin(input);
  }

  const response = await send("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email: input.email, password: input.password }),
  });

  if (!response) {
    return { ok: false, error: "server_unavailable" };
  }

  if (response.status === 200) {
    const body = await readBody<{ user?: AuthUser }>(response);
    return body?.user
      ? { ok: true, user: body.user }
      : { ok: false, error: "server_unavailable" };
  }

  if (response.status === 401) {
    return { ok: false, error: "invalid_credentials" };
  }

  if (response.status === 422) {
    const body = await readBody<{ fields?: Record<string, string> }>(response);
    return { ok: false, error: "validation", fields: body?.fields ?? {} };
  }

  return { ok: false, error: "server_unavailable" };
}

export async function logout(): Promise<LogoutResult> {
  if (MODE === "mock") {
    const { mockLogout } = await loadMock();
    return mockLogout();
  }

  const response = await send("/auth/logout", { method: "POST" });

  if (!response) {
    return { ok: false, error: "server_unavailable" };
  }

  return response.status === 204
    ? { ok: true }
    : { ok: false, error: "server_unavailable" };
}

export async function me(): Promise<MeResult> {
  if (MODE === "mock") {
    const { mockMe } = await loadMock();
    return mockMe();
  }

  const response = await send("/auth/me", { method: "GET" });

  if (!response) {
    return { ok: false, error: "server_unavailable" };
  }

  if (response.status === 200) {
    const body = await readBody<{ user?: AuthUser }>(response);
    return body?.user
      ? { ok: true, user: body.user }
      : { ok: false, error: "server_unavailable" };
  }

  if (response.status === 401) {
    return { ok: false, error: "unauthenticated" };
  }

  return { ok: false, error: "server_unavailable" };
}
