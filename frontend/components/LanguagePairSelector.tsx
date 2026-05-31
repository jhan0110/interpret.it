"use client";

import { SegmentedControl } from "./SegmentedControl";

/** Unordered language pair (alphabetically normalized). */
export type LanguagePair = "en-ko" | "en-es" | "ko-es";

export const LANGUAGE_PAIRS: LanguagePair[] = ["en-ko", "en-es", "ko-es"];

const PAIR_LABEL: Record<LanguagePair, string> = {
  "en-ko": "EN ↔ KO",
  "en-es": "EN ↔ ES",
  "ko-es": "KO ↔ ES",
};

const PAIR_ARIA: Record<LanguagePair, string> = {
  "en-ko": "English and Korean",
  "en-es": "English and Spanish",
  "ko-es": "Korean and Spanish",
};

type Props = {
  value: LanguagePair;
  onChange: (next: LanguagePair) => void;
  disabled?: boolean;
};

/**
 * Three-option segmented control for the learner's working language
 * pair. Sits on the home page; mastery + train form derive from it.
 *
 * The underlying `SegmentedControl` switches its semantic role
 * automatically when there are 3+ options (becomes a radiogroup with
 * arrow-key navigation) — no special handling required here.
 */
export function LanguagePairSelector({ value, onChange, disabled }: Props) {
  return (
    <SegmentedControl<LanguagePair>
      value={value}
      onChange={onChange}
      disabled={disabled}
      ariaLabel="Working language pair"
      options={LANGUAGE_PAIRS.map((p) => ({
        value: p,
        label: PAIR_LABEL[p],
        ariaLabel: PAIR_ARIA[p],
      }))}
    />
  );
}

/** Decompose a pair into its two language codes (alphabetical order). */
export function langsForPair(pair: LanguagePair): [string, string] {
  const [a, b] = pair.split("-");
  return [a, b];
}

/** Normalize an unordered (source, target) into the canonical pair. */
export function pairForLangs(a: string, b: string): LanguagePair | null {
  const [lo, hi] = [a, b].sort();
  const candidate = `${lo}-${hi}` as LanguagePair;
  return LANGUAGE_PAIRS.includes(candidate) ? candidate : null;
}
