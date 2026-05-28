"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import type { VocabCard } from "./page";

const GATEWAY_URL =
  process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

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
        <p className="text-xl font-semibold text-accent">Session complete</p>
        <p className="text-sm text-ink-faint">
          Reviewed {cards.length} card{cards.length !== 1 ? "s" : ""}.
        </p>
        <Button variant="ghost" onClick={() => router.refresh()}>
          Back to deck
        </Button>
      </div>
    );
  }

  if (!current) return null;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-ink-faint">
        {index + 1} / {cards.length}
      </p>

      <Card
        interactive
        as="button"
        onClick={() => setFlipped((f) => !f)}
        className="min-h-48 w-full text-left"
      >
        {!flipped ? (
          <div className="flex h-full flex-col justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-ink-faint">
                {current.source_lang} → {current.target_lang} · {current.domain}
              </p>
              <p className="mt-3 text-2xl font-semibold text-ink">{current.term}</p>
            </div>
            <p className="mt-4 text-xs text-ink-faint">tap to reveal</p>
          </div>
        ) : (
          <div className="flex h-full flex-col justify-between">
            <div>
              <p className="text-xs uppercase tracking-wide text-ink-faint">
                definition
              </p>
              <p className="mt-3 text-xl font-medium text-ink">
                {current.definition}
              </p>
              {current.register && (
                <p className="mt-2 text-xs text-ink-faint">{current.register}</p>
              )}
            </div>
            {current.gap_type && (
              <span
                className={[
                  "mt-4 inline-block rounded-[2px] px-2 py-0.5 text-[10px] uppercase tracking-wider",
                  current.gap_type === "knowledge_gap"
                    ? "border border-warning text-warning"
                    : "border border-ink-faint text-ink-soft",
                ].join(" ")}
              >
                {current.gap_type === "knowledge_gap"
                  ? "Knowledge gap"
                  : "Memory gap"}
              </span>
            )}
          </div>
        )}
      </Card>

      {flipped && (
        <div className="grid grid-cols-4 gap-2">
          <Button
            variant="ghost"
            onClick={() => grade(0)}
            disabled={submitting}
            className="border-critical text-critical hover:bg-[rgba(106,15,15,0.1)]"
          >
            Again
          </Button>
          <Button variant="ghost" onClick={() => grade(3)} disabled={submitting}>
            Hard
          </Button>
          <Button
            variant="ghost"
            onClick={() => grade(4)}
            disabled={submitting}
            className="border-accent text-accent"
          >
            Good
          </Button>
          <Button variant="primary" onClick={() => grade(5)} disabled={submitting}>
            Easy
          </Button>
        </div>
      )}
    </div>
  );
}
