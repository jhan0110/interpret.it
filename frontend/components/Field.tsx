"use client";

import type { InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";

const inputClass =
  "bg-paper-tint border border-ink-faint text-ink rounded-[2px] px-3 py-2 text-sm placeholder:text-ink-faint " +
  "transition-[border-color,box-shadow] duration-[120ms] ease-linear " +
  "focus:border-accent focus:outline-none focus:shadow-[0_0_0_3px_var(--accent-wash)] " +
  "disabled:opacity-50";

type FieldWrapperProps = {
  label: string;
  htmlFor?: string;
  hint?: ReactNode;
  helper?: ReactNode;
  children: ReactNode;
};

export function Field({ label, htmlFor, hint, helper, children }: FieldWrapperProps) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
        {hint ? <span className="ml-1 text-ink-faint">{hint}</span> : null}
      </label>
      {children}
      {helper ? <p className="text-xs text-ink-faint">{helper}</p> : null}
    </div>
  );
}

type TextFieldProps = InputHTMLAttributes<HTMLInputElement>;

export function TextInput({ className = "", ...rest }: TextFieldProps) {
  return <input className={`${inputClass} ${className}`.trim()} {...rest} />;
}

type AreaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function TextArea({ className = "", ...rest }: AreaProps) {
  return <textarea className={`${inputClass} ${className}`.trim()} {...rest} />;
}
