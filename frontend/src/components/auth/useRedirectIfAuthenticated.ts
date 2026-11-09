"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef } from "react";
import { useAuth } from "@/components/AuthProvider";

export function useRedirectIfAuthenticated(): { markLeaving: () => void } {
  const { status } = useAuth();
  const router = useRouter();
  const leaving = useRef(false);

  useEffect(() => {
    if (status === "authenticated" && !leaving.current) {
      router.replace("/chat");
    }
  }, [status, router]);

  const markLeaving = useCallback(() => {
    leaving.current = true;
  }, []);

  return { markLeaving };
}
