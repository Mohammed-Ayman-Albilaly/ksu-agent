"use client";

import type { ReactNode } from "react";
import Link from "next/link";

type AuthCardProps = {
  title: string;
  subtitle: string;
  switchText: string;
  switchLink: string;
  switchHref: string;
  children: ReactNode;
};

export function AuthCard({
  title,
  subtitle,
  switchText,
  switchLink,
  switchHref,
  children,
}: AuthCardProps) {
  return (
    <div className="rounded-2xl bg-white p-6 shadow-[0_24px_60px_-32px_rgba(14,42,71,0.5)] ring-1 ring-slate-200/70 sm:p-8">
      <h1 className="text-2xl font-bold text-navy">{title}</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted">{subtitle}</p>

      <div className="mt-6">{children}</div>

      <p className="mt-6 border-t border-slate-200 pt-5 text-center text-sm text-muted">
        {switchText}{" "}
        <Link
          href={switchHref}
          className="font-semibold text-teal-deep transition-colors hover:text-teal-dark"
        >
          {switchLink}
        </Link>
      </p>
    </div>
  );
}
