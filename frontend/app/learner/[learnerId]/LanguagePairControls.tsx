"use client";

import { useEffect, useRef, useState } from "react";
import { Card } from "@/components/Card";
import {
  LANGUAGE_PAIRS,
  LanguagePair,
  LanguagePairSelector,
  pairForLangs,
} from "@/components/LanguagePairSelector";

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

export const PAIR_STORAGE_KEY = "interpretit:language_pair";
export const PAIR_CHANGED_EVENT = "interpretit:pair-changed";
const DEFAULT_PAIR: LanguagePair = "en-ko";

const PAIR_LABEL: Record<LanguagePair, string> = {
  "en-ko": "EN ↔ KO",
  "en-es": "EN ↔ ES",
  "ko-es": "KO ↔ ES",
};

/** Read the persisted pair, or null if storage is unavailable / unset. */
function readStoredPair(): LanguagePair | null {
  try {
    const stored = localStorage.getItem(PAIR_STORAGE_KEY);
    if (stored && LANGUAGE_PAIRS.includes(stored as LanguagePair)) {
      return stored as LanguagePair;
    }
  } catch {
    // localStorage unavailable
  }
  return null;
}

/**
 * Custom hook: keep a `LanguagePair` in sync with localStorage AND
 * with other components on the page via a `PAIR_CHANGED_EVENT` event.
 * Setting via `setPair` writes localStorage and broadcasts; other
 * subscribers (the bottom mastery section) pick it up immediately.
 */
export function useLanguagePair(): [LanguagePair, (next: LanguagePair) => void] {
  const [pair, setPairState] = useState<LanguagePair>(DEFAULT_PAIR);
  useEffect(() => {
    const sync = () => {
      const fresh = readStoredPair();
      if (fresh) setPairState(fresh);
    };
    sync();
    window.addEventListener(PAIR_CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PAIR_CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);
  function setPair(next: LanguagePair) {
    setPairState(next);
    try {
      localStorage.setItem(PAIR_STORAGE_KEY, next);
    } catch {
      // ignore
    }
    try {
      window.dispatchEvent(new Event(PAIR_CHANGED_EVENT));
    } catch {
      // ignore
    }
  }
  return [pair, setPair];
}

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

type Props = {
  mastery: MasteryScore[];
};

/**
 * Compact pair-status button. Clicking opens the modal where the
 * learner can switch pair and inspect mastery across all pairs they
 * have data for.
 */
export function LanguagePairControls({ mastery }: Props) {
  const [pair, setPair] = useLanguagePair();
  const dialogRef = useRef<HTMLDialogElement | null>(null);

  function openModal() {
    dialogRef.current?.showModal();
  }
  function closeModal() {
    dialogRef.current?.close();
  }

  // Bucket mastery by unordered pair for the modal's per-pair display.
  const byPair = new Map<LanguagePair, MasteryScore[]>();
  for (const m of mastery) {
    const key = pairForLangs(m.source_lang, m.target_lang);
    if (!key) continue;
    const arr = byPair.get(key) ?? [];
    arr.push(m);
    byPair.set(key, arr);
  }
  for (const arr of byPair.values()) {
    arr.sort((a, b) => {
      const dd = a.domain.localeCompare(b.domain);
      if (dd !== 0) return dd;
      return (a.source_lang + a.target_lang).localeCompare(
        b.source_lang + b.target_lang,
      );
    });
  }

  // Sections to render in the modal: current pair always first, then
  // any other pair the learner has data for.
  const pairsWithData = LANGUAGE_PAIRS.filter((p) => byPair.has(p));
  const sectionsToShow = Array.from(new Set([pair, ...pairsWithData]));

  return (
    <>
      <button
        type="button"
        onClick={openModal}
        className="inline-flex items-center gap-2 self-start rounded-[2px] border border-ink-faint bg-paper px-3 py-1.5 font-mono text-xs uppercase tracking-wider text-ink-soft transition-[background-color,border-color] duration-[120ms] hover:border-accent hover:bg-accent-wash"
        aria-haspopup="dialog"
      >
        <span className="text-ink-faint">Working language</span>
        <span className="text-ink">{PAIR_LABEL[pair]}</span>
        <span aria-hidden className="text-accent">⚙</span>
      </button>

      <dialog
        ref={dialogRef}
        className="fixed inset-0 m-auto h-fit w-[min(100%-2rem,28rem)] rounded-[2px] border border-accent bg-paper p-0 text-ink shadow-[0_8px_24px_rgba(0,0,0,0.25)] backdrop:bg-[rgba(0,0,0,0.60)]"
        aria-label="Working language and mastery"
        onClick={(e) => {
          // Click-outside-to-close: backdrop click lands on the dialog
          // element itself (target === currentTarget) because the
          // dialog's inner content lives inside a child.
          if (e.target === e.currentTarget) closeModal();
        }}
      >
        <div className="flex flex-col gap-5 p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wider text-ink">
                Working language
              </h3>
              <p className="mt-1 text-xs text-ink-faint">
                Mastery and training are tracked per direction. Switch any
                time — sessions you start will use the selected pair.
              </p>
            </div>
            <button
              type="button"
              onClick={closeModal}
              className="rounded-[2px] border border-ink-faint px-2 py-0.5 font-mono text-xs text-ink-soft hover:border-accent hover:bg-accent-wash"
              aria-label="Close"
            >
              ✕
            </button>
          </div>

          <div className="flex flex-col gap-2">
            <LanguagePairSelector value={pair} onChange={setPair} />
            <p className="text-[10px] leading-relaxed text-ink-faint">
              Pairs anchor on English while the pipeline is validated.
              Interpretation between two non-English languages (e.g.
              KO ↔ ES) is under development and will appear here once
              the audio + evaluation paths are calibrated for
              non-English source content.
            </p>
          </div>

          <div>
            <h4 className="mb-2 text-[10px] font-medium uppercase tracking-wide text-ink-faint">
              Mastery by pair
            </h4>
            {sectionsToShow.map((p) => {
              const rows = byPair.get(p) ?? [];
              const isCurrent = p === pair;
              return (
                <details
                  key={p}
                  open={isCurrent}
                  className="mb-2 rounded-[2px] border border-accent/40 bg-paper"
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
        </div>
      </dialog>
    </>
  );
}

/**
 * Compact mastery list filtered to the currently-selected pair —
 * intended for the bottom-of-page "Mastery by domain" section.
 * Subscribes to PAIR_CHANGED_EVENT so it updates immediately when
 * the learner picks a new pair in the modal.
 */
export function CurrentPairMastery({ mastery }: Props) {
  const [pair] = useLanguagePair();
  const filtered = mastery
    .filter((m) => pairForLangs(m.source_lang, m.target_lang) === pair)
    .sort((a, b) => {
      const dd = a.domain.localeCompare(b.domain);
      if (dd !== 0) return dd;
      return (a.source_lang + a.target_lang).localeCompare(
        b.source_lang + b.target_lang,
      );
    });

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-wide text-ink-faint">
          Mastery by domain
        </p>
        <span className="font-mono text-[10px] text-ink-faint">
          {PAIR_LABEL[pair]}
        </span>
      </div>
      {filtered.length === 0 ? (
        <p className="text-sm text-ink-soft">
          No attempts on this pair yet &mdash; start a session above.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {filtered.map((m) => (
            <MasteryRow
              key={`${m.domain}:${m.source_lang}-${m.target_lang}`}
              score={m}
            />
          ))}
        </div>
      )}
    </div>
  );
}
