"use client";

import type { KeyboardEvent, ReactNode } from "react";

export type SegmentedOption<V extends string | number> = {
  value: V;
  label: ReactNode;
  ariaLabel?: string;
};

type Props<V extends string | number> = {
  value: V;
  onChange: (next: V) => void;
  options: SegmentedOption<V>[];
  ariaLabel?: string;
  disabled?: boolean;
  className?: string;
};

export function SegmentedControl<V extends string | number>({
  value,
  onChange,
  options,
  ariaLabel,
  disabled = false,
  className = "",
}: Props<V>) {
  const role = options.length === 2 ? "switch" : "radiogroup";
  const activeIndex = options.findIndex((o) => o.value === value);

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    const last = options.length - 1;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      if (options.length === 2) {
        const next = options[activeIndex === 0 ? 1 : 0];
        if (next.value !== value) onChange(next.value);
      }
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const idx = Math.max(0, activeIndex - 1);
      const next = options[idx];
      if (next.value !== value) onChange(next.value);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      const idx = Math.min(last, activeIndex + 1);
      const next = options[idx];
      if (next.value !== value) onChange(next.value);
    } else if (e.key === "Home") {
      e.preventDefault();
      if (options[0].value !== value) onChange(options[0].value);
    } else if (e.key === "End") {
      e.preventDefault();
      if (options[last].value !== value) onChange(options[last].value);
    }
  }

  const containerAria =
    role === "switch"
      ? { role: "switch", "aria-checked": activeIndex > 0 }
      : { role: "radiogroup" };

  return (
    <div
      {...containerAria}
      aria-label={ariaLabel}
      tabIndex={disabled ? -1 : 0}
      onKeyDown={handleKeyDown}
      className={[
        "inline-flex w-full overflow-hidden rounded-[2px] border border-accent bg-transparent",
        "focus:outline-none focus-visible:shadow-[0_0_0_3px_var(--accent-wash)]",
        disabled ? "opacity-40 cursor-not-allowed" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {options.map((opt, i) => {
        const selected = opt.value === value;
        const segmentRole = role === "switch" ? undefined : "radio";
        const segmentAria =
          role === "switch"
            ? { "aria-label": opt.ariaLabel ?? undefined }
            : { "aria-checked": selected, "aria-label": opt.ariaLabel ?? undefined };
        return (
          <button
            key={String(opt.value)}
            type="button"
            role={segmentRole}
            tabIndex={-1}
            disabled={disabled}
            onClick={() => {
              if (!disabled && !selected) onChange(opt.value);
            }}
            {...segmentAria}
            className={[
              "flex flex-1 items-center justify-center px-3 py-2 text-sm font-medium",
              "transition-[background-color,color] duration-[120ms] ease-linear",
              i > 0 ? "border-l border-accent" : "",
              selected
                ? "bg-accent text-paper"
                : "bg-transparent text-ink hover:bg-accent-wash",
              disabled ? "cursor-not-allowed" : "cursor-pointer",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
