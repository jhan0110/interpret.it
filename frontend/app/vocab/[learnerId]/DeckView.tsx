"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { VocabCard } from "./page";

const GATEWAY_URL =
  process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

const GRADES = [
  { grade: 0, label: "Again", className: "bg-red-900/60 hover:bg-red-800 text-red-200" },
  { grade: 3, label: "Hard", className: "bg-zinc-700 hover:bg-zinc-600 text-zinc-200" },
  { grade: 4, label: "Good", className: "bg-zinc-600 hover:bg-zinc-500 text-zinc-100" },
  { grade: 5, label: "Easy", className: "bg-emerald-700 hover:bg-emerald-600 text-emerald-100" },
] as const;

export function DeckView({
  learnerId,
  initialCards,
}: {
  learnerId: string;
  initialCards: VocabCard[];
}) {
  const router = useRouter();
  const [cards, setCards] = useState<VocabCard[]>(initialCards);
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const current = cards[index];

  async function grade(g: number) {
    if (!current || submitting) return;
    setSubmitting(true);
    try {
      await fetch(
        `${GATEWAY_URL}/learners/${learnerId}/vocab/${current.deck_id}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ grade: g }),
        },
      );
    } catch {
      // best-effort; advance regardless
    }
    const next = index + 1;
    if (next >= cards.length) {
      setDone(true);
    } else {
      setIndex(next);
      setFlipped(false);
    }
    setSubmitting(false);
  }

  if (done) {
    return (
      <div className="flex flex-col items-center gap-4 py-12 text-center">
        <p className="text-xl font-semibold text-emerald-400">
          Session complete
        </p>
        <p className="text-sm text-zinc-400">
          Reviewed {cards.length} card{cards.length !== 1 ? "s" : ""}.
        </p>
        <button
          onClick={() => router.refresh()}
          className="rounded bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
        >
          Back to deck
        </button>
      </div>
    );
  }

  if (!current) return null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-zinc-500">
        {index + 1} / {cards.length}
      </p>

      <button
        onClick={() => setFlipped((f) => !f)}
        className="min-h-48 w-full rounded-xl border border-zinc-700 bg-zinc-900 p-6 text-left transition-colors hover:border-zinc-600"
      >
        {!flipped ? (
          <div className="flex h-full flex-col justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                {current.source_lang} → {current.target_lang} · {current.domain}
              </p>
              <p className="mt-3 text-2xl font-semibold">{current.term}</p>
            </div>
            <p className="mt-4 text-xs text-zinc-600">tap to reveal</p>
          </div>
        ) : (
          <div className="flex h-full flex-col justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                definition
              </p>
              <p className="mt-3 text-xl font-medium text-emerald-300">
                {current.definition}
              </p>
              {current.register && (
                <p className="mt-2 text-xs text-zinc-500">{current.register}</p>
              )}
            </div>
            {current.gap_type && (
              <span
                className={[
                  "mt-4 inline-block rounded-full px-2 py-0.5 text-xs font-medium",
                  current.gap_type === "knowledge_gap"
                    ? "bg-amber-900/40 text-amber-300"
                    : "bg-blue-900/40 text-blue-300",
                ].join(" ")}
              >
                {current.gap_type === "knowledge_gap"
                  ? "Knowledge gap"
                  : "Memory gap"}
              </span>
            )}
          </div>
        )}
      </button>

      {flipped && (
        <div className="grid grid-cols-4 gap-2">
          {GRADES.map(({ grade: g, label, className }) => (
            <button
              key={g}
              onClick={() => grade(g)}
              disabled={submitting}
              className={[
                "rounded px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50",
                className,
              ].join(" ")}
            >
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
