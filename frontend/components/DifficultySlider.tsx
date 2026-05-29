"use client";

import { useEffect, useRef, useState } from "react";

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

const clampToInt = (n: number): 1 | 2 | 3 | 4 | 5 => {
  const r = Math.round(n);
  return Math.max(1, Math.min(5, r)) as 1 | 2 | 3 | 4 | 5;
};

export function DifficultySlider({
  value,
  onChange,
  options,
  disabled = false,
}: DifficultySliderProps) {
  const [dragValue, setDragValue] = useState<number>(value);
  const draggingRef = useRef(false);

  useEffect(() => {
    if (!draggingRef.current) setDragValue(value);
  }, [value]);

  const pct = ((dragValue - 1) / 4) * 100;
  const currentOption = options.find((o) => o.value === clampToInt(dragValue));
  const descriptiveLabel =
    currentOption?.label.replace(/^\d+\s*—\s*/, "") ?? String(value);

  function commitSnap() {
    draggingRef.current = false;
    const snapped = clampToInt(dragValue);
    setDragValue(snapped);
    if (snapped !== value) onChange(snapped);
  }

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
                className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2"
                style={{
                  left: `${tickPct}%`,
                  width: "3px",
                  height: "3px",
                  background: "var(--ink-faint)",
                }}
              />
            );
          })}
        </div>

        <div className="relative -mt-5 h-5 w-full">
          <div
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-0 h-0.5 -translate-y-1/2"
            style={{
              width: `${pct}%`,
              background: "var(--accent)",
              transition: draggingRef.current
                ? "none"
                : "width 140ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
          />
          <div
            aria-hidden
            className="pointer-events-none absolute top-1/2 right-0 h-0.5 -translate-y-1/2"
            style={{
              width: `${100 - pct}%`,
              background: "var(--ink-faint)",
              transition: draggingRef.current
                ? "none"
                : "width 140ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
          />

          <span
            aria-hidden
            className="pointer-events-none absolute top-1/2"
            style={{
              left: `${pct}%`,
              transform: "translate(-50%, -50%)",
              width: 18,
              height: 18,
              borderRadius: 2,
              background: "#1F4D2E",
              boxShadow: "0 0 0 1px var(--paper)",
              transition: draggingRef.current
                ? "none"
                : "left 140ms cubic-bezier(0.22, 1, 0.36, 1)",
            }}
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
              width: 28px;
              height: 28px;
              background: transparent;
              border: none;
              margin-top: -13px;
              cursor: pointer;
            }
            .difficulty-range::-moz-range-thumb {
              width: 28px;
              height: 28px;
              background: transparent;
              border: none;
              cursor: pointer;
            }
            .difficulty-range:focus-visible {
              outline: none;
            }
          `}</style>

          <input
            type="range"
            min={1}
            max={5}
            step={0.001}
            value={dragValue}
            disabled={disabled}
            aria-label="Difficulty level"
            aria-valuetext={descriptiveLabel}
            aria-valuemin={1}
            aria-valuemax={5}
            aria-valuenow={clampToInt(dragValue)}
            onPointerDown={() => {
              draggingRef.current = true;
            }}
            onPointerUp={commitSnap}
            onPointerCancel={commitSnap}
            onBlur={() => {
              if (draggingRef.current) commitSnap();
            }}
            onChange={(e) => setDragValue(Number(e.target.value))}
            onKeyDown={(e) => {
              if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
                e.preventDefault();
                const delta = e.key === "ArrowRight" ? 1 : -1;
                const next = clampToInt(clampToInt(dragValue) + delta);
                setDragValue(next);
                if (next !== value) onChange(next);
              } else if (e.key === "Home") {
                e.preventDefault();
                setDragValue(1);
                if (value !== 1) onChange(1);
              } else if (e.key === "End") {
                e.preventDefault();
                setDragValue(5);
                if (value !== 5) onChange(5);
              }
            }}
            className="difficulty-range absolute inset-0 z-10"
          />
        </div>
      </div>

      <p className="text-center text-sm text-ink-soft">
        {currentOption?.label ?? value}
      </p>
    </div>
  );
}
