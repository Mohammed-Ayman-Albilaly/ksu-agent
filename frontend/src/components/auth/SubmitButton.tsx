"use client";

import { useLanguage } from "@/components/LanguageProvider";

type SubmitButtonProps = {
  label: string;
  pending: boolean;
};

export function SubmitButton({ label, pending }: SubmitButtonProps) {
  const { t } = useLanguage();

  return (
    <button
      type="submit"
      disabled={pending}
      aria-busy={pending}
      className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-teal-deep px-4 py-3 text-sm font-semibold text-white transition-colors hover:bg-teal-dark disabled:cursor-not-allowed disabled:opacity-70"
    >
      {pending ? (
        <>
          <span
            aria-hidden="true"
            className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white motion-reduce:animate-none"
          />
          {t.auth.pending}
        </>
      ) : (
        label
      )}
    </button>
  );
}
