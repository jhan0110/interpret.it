"use client";

import { SegmentedControl } from "@/components/SegmentedControl";

type LanguageSwitchProps = {
  value: "en" | "ko";
  onChange: (next: "en" | "ko") => void;
  disabled?: boolean;
};

export function LanguageSwitch({ value, onChange, disabled = false }: LanguageSwitchProps) {
  return (
    <SegmentedControl
      value={value}
      onChange={onChange}
      disabled={disabled}
      ariaLabel="Language"
      options={[
        { value: "en" as const, label: "EN", ariaLabel: "Switch to English" },
        { value: "ko" as const, label: "한국어", ariaLabel: "Switch to Korean" },
      ]}
    />
  );
}
