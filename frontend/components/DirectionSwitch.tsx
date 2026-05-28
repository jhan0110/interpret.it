"use client";

import { SegmentedControl } from "@/components/SegmentedControl";

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
  return (
    <SegmentedControl
      value={value}
      onChange={onChange}
      disabled={disabled}
      ariaLabel="Translation direction"
      options={[
        { value: "en-ko" as const, label: "EN → 한국어" },
        { value: "ko-en" as const, label: "한국어 → EN" },
      ]}
    />
  );
}
