// DEVELOPMENT ONLY. Not secure. Replaced by the real API when NEXT_PUBLIC_AUTH_MODE=api.

import type {
  AuthResult,
  AuthUser,
  LoginInput,
  LogoutResult,
  MeResult,
  RegisterInput,
} from "./auth";

const USERS_KEY = "ksu-agent-mock-users";
const SESSION_KEY = "ksu-agent-mock-session";
const DELAY_MS = 600;

type StoredUser = AuthUser & { password_hash: string };

type StoredSession = { user_id: string };

function wait(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, DELAY_MS);
  });
}

function readUsers(): StoredUser[] {
  try {
    const raw = window.localStorage.getItem(USERS_KEY);

    if (!raw) {
      return [];
    }

    const parsed: unknown = JSON.parse(raw);

    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed.filter((entry): entry is StoredUser => {
      if (!entry || typeof entry !== "object") {
        return false;
      }

      const candidate = entry as Partial<StoredUser>;

      return (
        typeof candidate.id === "string" &&
        typeof candidate.full_name === "string" &&
        typeof candidate.email === "string" &&
        typeof candidate.password_hash === "string"
      );
    });
  } catch {
    return [];
  }
}

function writeUsers(users: StoredUser[]): boolean {
  try {
    window.localStorage.setItem(USERS_KEY, JSON.stringify(users));
    return true;
  } catch {
    return false;
  }
}

function readSession(): StoredSession | null {
  try {
    const raw = window.localStorage.getItem(SESSION_KEY);

    if (!raw) {
      return null;
    }

    const parsed: unknown = JSON.parse(raw);

    if (!parsed || typeof parsed !== "object") {
      return null;
    }

    const userId = (parsed as { user_id?: unknown }).user_id;

    return typeof userId === "string" ? { user_id: userId } : null;
  } catch {
    return null;
  }
}

function writeSession(session: StoredSession | null): boolean {
  try {
    if (!session) {
      window.localStorage.removeItem(SESSION_KEY);
      return true;
    }

    window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
    return true;
  } catch {
    return false;
  }
}

function createId(): string {
  try {
    if (typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
  } catch {
    // Fall through to a non-crypto identifier.
  }

  return `mock-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

async function hashPassword(password: string): Promise<string> {
  try {
    const bytes = new TextEncoder().encode(password);
    const digest = await crypto.subtle.digest("SHA-256", bytes);

    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    let hash = 2166136261;

    for (let index = 0; index < password.length; index += 1) {
      hash ^= password.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }

    return `fnv-${(hash >>> 0).toString(16)}`;
  }
}

function toPublicUser(user: StoredUser): AuthUser {
  return { id: user.id, full_name: user.full_name, email: user.email };
}

export async function mockRegister(input: RegisterInput): Promise<AuthResult> {
  await wait();

  const email = input.email.trim().toLowerCase();
  const users = readUsers();

  if (users.some((user) => user.email === email)) {
    return { ok: false, error: "email_taken" };
  }

  const user: StoredUser = {
    id: createId(),
    full_name: input.fullName.trim(),
    email,
    password_hash: await hashPassword(input.password),
  };

  if (!writeUsers([...users, user]) || !writeSession({ user_id: user.id })) {
    return { ok: false, error: "server_unavailable" };
  }

  return { ok: true, user: toPublicUser(user) };
}

export async function mockLogin(input: LoginInput): Promise<AuthResult> {
  await wait();

  const email = input.email.trim().toLowerCase();
  const passwordHash = await hashPassword(input.password);
  const user = readUsers().find((entry) => entry.email === email);

  if (!user || user.password_hash !== passwordHash) {
    return { ok: false, error: "invalid_credentials" };
  }

  if (!writeSession({ user_id: user.id })) {
    return { ok: false, error: "server_unavailable" };
  }

  return { ok: true, user: toPublicUser(user) };
}

export async function mockLogout(): Promise<LogoutResult> {
  await wait();
  writeSession(null);
  return { ok: true };
}

export async function mockMe(): Promise<MeResult> {
  const session = readSession();

  if (!session) {
    return { ok: false, error: "unauthenticated" };
  }

  const user = readUsers().find((entry) => entry.id === session.user_id);

  if (!user) {
    writeSession(null);
    return { ok: false, error: "unauthenticated" };
  }

  return { ok: true, user: toPublicUser(user) };
}
