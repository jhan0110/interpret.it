"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import {
  LANGUAGE_PAIRS,
  LanguagePair,
  LanguagePairSelector,
  pairForLangs,
} from "@/components/LanguagePairSelector";

/** Mirror of the server's MasteryScore shape — only the fields we render. */
interface MasteryScore {
  domain: string;
  source_lang: "en" | "ko" | "es";
  target_lang: "en" | "ko" | "es";
  tier: number;
  tier_name: string;
  next_tier_name: string | null;
  progress: number;
  attempts_count: number;
}

const STORAGE_KEY = "interpretit:language_pair";
const DEFAULT_PAIR: LanguagePair = "en-ko";

function MasteryRow({ score }: { score: MasteryScore }) {
  const pct = Math.round((score.progress ?? 0) * 100);
  const atMaster = score.next_tier_name === null;
  return (
    <div className="flex flex-col gap-1 border-b border-accent pb-2 last:border-0 last:pb-0">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium uppercase tracking-wider text-ink-soft text-xs">
          {score.domain}
          <span className="ml-2 font-mono text-[10px] text-ink-faint">
            {score.source_lang} → {score.target_lang}
          </span>
        </span>
        <span className="font-semibold uppercase tracking-wider text-accent text-xs">
          {score.tier_name}
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-[1px] bg-paper-tint">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <div className="flex items-center justify-between text-[10px] text-ink-faint">
        <span>{score.attempts_count} attempts</span>
        {atMaster ? (
          <span>Master tier reached</span>
        ) : (
          <span>
            {pct}% to {score.next_tier_name}
          </span>
        )}
      </div>
    </div>
  );
}

const PAIR_LABEL: Record<LanguagePair, string> = {
  "en-ko": "EN ↔ KO",
  "en-es": "EN ↔ ES",
  "ko-es": "KO ↔ ES",
};

type Props = {
  mastery: MasteryScore[];
};

/**
 * Working-language selector + mastery display grouped per pair as
 * collapsible sections. The currently-selected pair (persisted to
 * localStorage) auto-expands; other pairs are collapsed by default.
 */
export function LanguagePairSection({ mastery }: Props) {
  const [pair, setPair] = useState<LanguagePair>(DEFAULT_PAIR);
  // Hydrate from localStorage after mount to avoid SSR/CSR mismatch.
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && LANGUAGE_PAIRS.includes(stored as LanguagePair)) {
        setPair(stored as LanguagePair);
      }
    } catch {
      // localStorage unavailable (SSR / disabled storage) — keep default.
    }
  }, []);

  function handleChange(next: LanguagePair) {
    setPair(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore quota / disabled storage
    }
  }

  // Bucket mastery rows by unordered pair.
  const byPair = new Map<LanguagePair, MasteryScore[]>();
  for (const m of mastery) {
    const key = pairForLangs(m.source_lang, m.target_lang);
    if (!key) continue;
    const arr = byPair.get(key) ?? [];
    arr.push(m);
    byPair.set(key, arr);
  }

  // Stable per-section order inside: by domain, then direction.
  for (const arr of byPair.values()) {
    arr.sort((a, b) => {
      const dd = a.domain.localeCompare(b.domain);
      if (dd !== 0) return dd;
      return (a.source_lang + a.target_lang).localeCompare(
        b.source_lang + b.target_lang,
      );
    });
  }

  // Render sections only for pairs the learner has data for. If the
  // currently-selected pair has no data yet, show an empty notice
  // inside its section so the user sees the selection is active.
  const pairsWithData = LANGUAGE_PAIRS.filter((p) => byPair.has(p));
  const sectionsToShow =
    pairsWithData.length === 0 ? [pair] : Array.from(new Set([pair, ...pairsWithData]));

  return (
    <section className="flex flex-col gap-4">
      <div>
        <h3 className="mb-2 text-[10px] font-medium uppercase tracking-wide text-ink-faint">
          Working language
        </h3>
        <LanguagePairSelector value={pair} onChange={handleChange} />
        <p className="mt-2 text-xs text-ink-faint">
          Mastery and training are tracked per language pair.
        </p>
      </div>

      <div>
        <h3 className="mb-3 text-[10px] font-medium uppercase tracking-wide text-ink-faint">
          Mastery by domain
        </h3>
        {sectionsToShow.map((p) => {
          const rows = byPair.get(p) ?? [];
          const isCurrent = p === pair;
          return (
            <details
              key={p}
              open={isCurrent}
              className="mb-3 rounded-[2px] border border-accent/40 bg-paper"
            >
              <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium uppercase tracking-wider text-ink-soft hover:bg-paper-tint">
                {PAIR_LABEL[p]}
                {isCurrent ? (
                  <span className="ml-2 font-mono text-[10px] text-accent">
                    selected
                  </span>
                ) : null}
                <span className="ml-2 font-mono text-[10px] text-ink-faint">
                  {rows.length} {rows.length === 1 ? "row" : "rows"}
                </span>
              </summary>
              <Card className="m-2 p-3">
                {rows.length === 0 ? (
                  <p className="text-sm text-ink-soft">
                    No attempts on this pair yet.
                  </p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {rows.map((m) => (
                      <MasteryRow
                        key={`${m.domain}:${m.source_lang}-${m.target_lang}`}
                        score={m}
                      />
                    ))}
                  </div>
                )}
              </Card>
            </details>
          );
        })}
      </div>
    </section>
  );
}
