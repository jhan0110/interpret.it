"use client";

export type Direction = "en-ko" | "ko-en";

type DirectionSwitchProps = {
  value: Direction;
  onChange: (next: Direction) => void;
  disabled?: boolean;
};

export function LanguageDirectionLabel({ value }: { value: Direction }) {
  return value === "en-ko" ? <>EN → 한국어</> : <>한국어 → EN</>;
}

export function DirectionSwitch({ value, onChange, disabled = false }: DirectionSwitchProps) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (disabled) return;
    if (e.key === " " || e.key === "Enter") {
      e.preventDefault();
      onChange(value === "en-ko" ? "ko-en" : "en-ko");
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      if (value !== "en-ko") onChange("en-ko");
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      if (value !== "ko-en") onChange("ko-en");
    }
  }

  const activeClass = "text-white";
  const inactiveClass = "text-zinc-400";
  const disabledClass = "opacity-40 cursor-not-allowed";

  return (
    <div
      role="switch"
      aria-checked={value === "ko-en"}
      aria-label="Translation direction"
      tabIndex={disabled ? -1 : 0}
      onKeyDown={handleKeyDown}
      className={`inline-flex h-9 w-full overflow-hidden rounded-full border border-zinc-700 bg-zinc-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#001b69] focus-visible:ring-offset-1 ${disabled ? disabledClass : ""}`}
    >
      <button
        type="button"
        aria-label="English to Korean"
        tabIndex={-1}
        disabled={disabled}
        onClick={() => {
          if (!disabled && value !== "en-ko") onChange("en-ko");
        }}
        style={value === "en-ko" ? { background: "#001b69" } : undefined}
        className={`flex flex-1 items-center justify-center text-sm font-medium transition-colors ${value === "en-ko" ? activeClass : inactiveClass} ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}
      >
        EN → 한국어
      </button>
      <button
        type="button"
        aria-label="Korean to English"
        tabIndex={-1}
        disabled={disabled}
        onClick={() => {
          if (!disabled && value !== "ko-en") onChange("ko-en");
        }}
        style={value === "ko-en" ? { background: "#001b69" } : undefined}
        className={`flex flex-1 items-center justify-center text-sm font-medium transition-colors ${value === "ko-en" ? activeClass : inactiveClass} ${disabled ? "cursor-not-allowed" : "cursor-pointer"}`}
      >
        한국어 → EN
      </button>
    </div>
  );
}
