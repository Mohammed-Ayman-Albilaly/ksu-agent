type IconProps = {
  className?: string;
};

const strokeProps = {
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round",
  strokeLinejoin: "round",
} as const;

export function BrandMark({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 32 32"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect width="32" height="32" rx="8" fill="#0E2A47" />
      <rect x="6" y="9" width="20" height="12" rx="4" fill="#17A398" />
      <path d="M11 20h4.5L11 24.6V20Z" fill="#17A398" />
      <circle cx="12" cy="15" r="1.4" fill="#0E2A47" />
      <circle cx="16" cy="15" r="1.4" fill="#0E2A47" />
      <circle cx="20" cy="15" r="1.4" fill="#0E2A47" />
    </svg>
  );
}

export function MenuIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
      strokeWidth={2}
    >
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
    </svg>
  );
}

export function CloseIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
      strokeWidth={2}
    >
      <path d="m6 6 12 12" />
      <path d="m18 6-12 12" />
    </svg>
  );
}

export function CitedIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="M7 3.5h6l5 5v11a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19.5v-15A1.5 1.5 0 0 1 7.5 3.5Z" />
      <path d="M13 3.5V9h5" />
      <path d="m9.2 14.6 1.9 1.9 3.9-4" />
    </svg>
  );
}

export function LanguagesIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <circle cx="12" cy="12" r="8.5" />
      <path d="M3.5 12h17" />
      <path d="M12 3.5c2.2 2.4 3.3 5.4 3.3 8.5s-1.1 6.1-3.3 8.5c-2.2-2.4-3.3-5.4-3.3-8.5S9.8 5.9 12 3.5Z" />
    </svg>
  );
}

export function HonestIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="M20 11.6c0 3.9-3.6 7.1-8 7.1-.9 0-1.8-.1-2.6-.4L5 20l1.1-3.2A6.8 6.8 0 0 1 4 11.6c0-3.9 3.6-7.1 8-7.1s8 3.2 8 7.1Z" />
      <path d="M10.4 10a1.75 1.75 0 1 1 2.5 1.6c-.6.3-1 .8-1 1.4v.4" />
      <path d="M11.9 16.1h.01" />
    </svg>
  );
}

export function CapIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="M3 9.5 12 5l9 4.5-9 4.5-9-4.5Z" />
      <path d="M6.5 11.6v4.1c0 1.6 2.5 2.8 5.5 2.8s5.5-1.2 5.5-2.8v-4.1" />
      <path d="M21 9.5v5" />
    </svg>
  );
}

export function LinkIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
      strokeWidth={2}
    >
      <path d="M10.6 13.4a4 4 0 0 0 5.6 0l2.3-2.3a4 4 0 0 0-5.6-5.6l-1.2 1.2" />
      <path d="M13.4 10.6a4 4 0 0 0-5.6 0l-2.3 2.3a4 4 0 0 0 5.6 5.6l1.2-1.2" />
    </svg>
  );
}

export function InfoIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5.2" />
      <path d="M12 7.9h.01" />
    </svg>
  );
}

export function EyeIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="M2.6 12S6.2 5.9 12 5.9 21.4 12 21.4 12 17.8 18.1 12 18.1 2.6 12 2.6 12Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function EyeOffIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="m3.5 3.5 17 17" />
      <path d="M10.2 6.2A9.4 9.4 0 0 1 12 6c5.8 0 9.4 6 9.4 6a17.6 17.6 0 0 1-3.1 3.7" />
      <path d="M6.3 7.9A17.2 17.2 0 0 0 2.6 12S6.2 18 12 18a9.6 9.6 0 0 0 3.5-.7" />
      <path d="M9.9 10a3 3 0 0 0 4.2 4.2" />
    </svg>
  );
}

export function SendIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="M20.5 3.5 3.9 10.2c-.7.3-.7 1.3 0 1.6l6.1 2.2 2.2 6.1c.3.7 1.3.7 1.6 0L20.5 3.5Z" />
      <path d="m10 14 4.6-4.6" />
    </svg>
  );
}

export function PlusIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
      strokeWidth={2}
    >
      <path d="M12 5v14" />
      <path d="M5 12h14" />
    </svg>
  );
}

export function StopIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <rect x="7" y="7" width="10" height="10" rx="2.5" />
    </svg>
  );
}

export function ArrowDownIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
      strokeWidth={2}
    >
      <path d="M12 5v14" />
      <path d="m6 13 6 6 6-6" />
    </svg>
  );
}

export function CopyIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <rect x="9" y="9" width="11" height="11" rx="2.5" />
      <path d="M15 6.5A2.5 2.5 0 0 0 12.5 4H6.5A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15" />
    </svg>
  );
}

export function CheckIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
      strokeWidth={2}
    >
      <path d="m5 12.5 4.5 4.5L19 7.5" />
    </svg>
  );
}

export function RefreshIcon({ className }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      aria-hidden="true"
      xmlns="http://www.w3.org/2000/svg"
      {...strokeProps}
    >
      <path d="M20 12a8 8 0 1 1-2.4-5.7" />
      <path d="M20 4v4h-4" />
    </svg>
  );
}
