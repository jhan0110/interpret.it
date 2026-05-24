"use client";

type LanguageSwitchProps = {
  value: "en" | "ko";
  onChange: (next: "en" | "ko") => void;
  disabled?: boolean;
};

export function LanguageSwitch({ value, onChange, disabled = false }: LanguageSwitchProps) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onChange(value === "en" ? "ko" : "en");
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (value !== "en") onChange("en");
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (value !== "ko") onChange("ko");
    }
  }

  const activeClass = "bg-zinc-900 text-white";
  const inactiveClass = "bg-zinc-100 text-zinc-600";
  const disabledClass = "opacity-40 cursor-not-allowed";

  return (
    <div
      role="switch"
      aria-checked={value === "ko"}
      aria-label="Language"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={handleKeyDown}
      className={`inline-flex h-9 w-full overflow-hidden rounded-full border border-zinc-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-500 focus-visible:ring-offset-1 ${disabled ? disabledClass : ""}`}
    >
      <button
        type="button"
        aria-label="Switch to English"
        tabIndex={-1}
        disabled={disabled}
        onClick={() => {
          if (!disabled && value !== "en") onChange("en");
        }}
        className={`flex flex-1 items-center justify-center text-sm font-medium transition-colors ${value === "en" ? activeClass : inactiveClass} ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}
      >
        EN
      </button>
      <button
        type="button"
        aria-label="Switch to Korean"
        tabIndex={-1}
        disabled={disabled}
        onClick={() => {
          if (!disabled && value !== "ko") onChange("ko");
        }}
        className={`flex flex-1 items-center justify-center text-sm font-medium transition-colors ${value === "ko" ? activeClass : inactiveClass} ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}
      >
        한국어
      </button>
    </div>
  );
}
