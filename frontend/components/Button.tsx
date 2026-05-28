"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "ghost" | "link";

type ButtonProps = {
  variant?: Variant;
  className?: string;
  children?: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>;

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-paper border border-accent hover:bg-accent-strong hover:border-accent-strong active:translate-y-px px-4 py-2 rounded-[2px] text-sm font-medium",
  ghost:
    "bg-transparent text-ink border border-ink-faint hover:bg-accent-wash hover:border-accent px-4 py-2 rounded-[2px] text-sm font-medium",
  link:
    "bg-transparent text-accent p-0 underline-offset-2 hover:underline text-sm",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  type,
  ...rest
}: ButtonProps) {
  const base =
    "transition-[background-color,border-color,transform] duration-[120ms] ease-linear disabled:cursor-not-allowed disabled:opacity-50";
  return (
    <button
      type={type ?? "button"}
      className={`${base} ${VARIANTS[variant]} ${className}`.trim()}
      {...rest}
    >
      {children}
    </button>
  );
}
