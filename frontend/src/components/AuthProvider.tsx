"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  login as loginRequest,
  logout as logoutRequest,
  me,
  register as registerRequest,
  type AuthResult,
  type AuthUser,
  type LoginInput,
  type RegisterInput,
} from "@/lib/api/auth";
import { clearChatSessions } from "@/lib/chatStorage";

export type AuthStatus = "loading" | "authenticated" | "guest";

type AuthContextValue = {
  user: AuthUser | null;
  status: AuthStatus;
  login: (input: LoginInput) => Promise<AuthResult>;
  register: (input: RegisterInput) => Promise<AuthResult>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");

  useEffect(() => {
    let active = true;

    void me().then((result) => {
      if (!active) {
        return;
      }

      if (result.ok) {
        setUser(result.user);
        setStatus("authenticated");
      } else {
        setUser(null);
        setStatus("guest");
      }
    });

    return () => {
      active = false;
    };
  }, []);

  const refresh = useCallback(async () => {
    const result = await me();

    if (result.ok) {
      setUser(result.user);
      setStatus("authenticated");
    } else {
      setUser(null);
      setStatus("guest");
    }
  }, []);

  const login = useCallback(async (input: LoginInput) => {
    const result = await loginRequest(input);

    if (result.ok) {
      setUser(result.user);
      setStatus("authenticated");
    }

    return result;
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const result = await registerRequest(input);

    if (result.ok) {
      setUser(result.user);
      setStatus("authenticated");
    }

    return result;
  }, []);

  const logout = useCallback(async () => {
    await logoutRequest();
    clearChatSessions();
    setUser(null);
    setStatus("guest");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, status, login, register, logout, refresh }),
    [user, status, login, register, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);

  if (!context) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }

  return context;
}
