"use client";

type DifficultyOption = {
  value: 1 | 2 | 3 | 4 | 5;
  label: string;
};

type DifficultySliderProps = {
  value: 1 | 2 | 3 | 4 | 5;
  onChange: (next: 1 | 2 | 3 | 4 | 5) => void;
  options: DifficultyOption[];
  disabled?: boolean;
};

export function DifficultySlider({
  value,
  onChange,
  options,
  disabled = false,
}: DifficultySliderProps) {
  const pct = ((value - 1) / 4) * 100;
  const currentOption = options.find((o) => o.value === value);
  const descriptiveLabel = currentOption?.label.replace(/^\d+\s*—\s*/, "") ?? String(value);

  return (
    <div className={`flex flex-col gap-2 ${disabled ? "opacity-40" : ""}`}>
      <div className="relative flex flex-col">
        <div className="relative h-5 w-full">
          {options.map((opt, i) => {
            const tickPct = (i / (options.length - 1)) * 100;
            return (
              <span
                key={opt.value}
                aria-hidden
                className="absolute top-1/2 h-2 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-zinc-300"
                style={{ left: `${tickPct}%` }}
              />
            );
          })}
        </div>

        <div className="relative -mt-5 h-5 w-full">
          <div
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-0 h-0.5 -translate-y-1/2 bg-zinc-900 transition-all"
            style={{ width: `${pct}%` }}
          />
          <div
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-0 h-0.5 -translate-y-1/2 bg-zinc-200"
            style={{ width: `${100 - pct}%` }}
          />

          <style>{`
            .difficulty-range {
              -webkit-appearance: none;
              appearance: none;
              background: transparent;
              cursor: pointer;
              height: 20px;
              width: 100%;
            }
            .difficulty-range:disabled {
              cursor: not-allowed;
            }
            .difficulty-range::-webkit-slider-runnable-track {
              background: transparent;
              height: 2px;
            }
            .difficulty-range::-moz-range-track {
              background: transparent;
              height: 2px;
            }
            .difficulty-range::-webkit-slider-thumb {
              -webkit-appearance: none;
              appearance: none;
              width: 18px;
              height: 18px;
              border-radius: 50%;
              background: #18181b;
              margin-top: -8px;
              transition: transform 0.1s;
            }
            .difficulty-range:not(:disabled)::-webkit-slider-thumb:hover {
              transform: scale(1.15);
            }
            .difficulty-range:focus-visible::-webkit-slider-thumb {
              outline: 2px solid #18181b;
              outline-offset: 2px;
            }
            .difficulty-range::-moz-range-thumb {
              border: none;
              width: 18px;
              height: 18px;
              border-radius: 50%;
              background: #18181b;
            }
          `}</style>

          <input
            type="range"
            min={1}
            max={5}
            step={1}
            value={value}
            disabled={disabled}
            aria-label="Difficulty level"
            aria-valuetext={descriptiveLabel}
            onChange={(e) => {
              const next = Number(e.target.value) as 1 | 2 | 3 | 4 | 5;
              onChange(next);
            }}
            className="difficulty-range absolute inset-0 z-10"
          />
        </div>
      </div>

      <p className="text-center text-sm text-zinc-700">
        {currentOption?.label ?? value}
      </p>
    </div>
  );
}
