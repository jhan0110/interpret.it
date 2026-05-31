"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { DeckView } from "./DeckView";
import { TopicSelector } from "./TopicSelector";
import {
  LANGUAGE_PAIRS,
  LanguagePair,
} from "@/components/LanguagePairSelector";
import type { VocabCard, VocabStats, TopicItem } from "./page";

const PAIR_STORAGE_KEY = "interpretit:language_pair";
const PAIR_CHANGED_EVENT = "interpretit:pair-changed";
const DEFAULT_PAIR: LanguagePair = "en-ko";

const PAIR_LABEL: Record<LanguagePair, string> = {
  "en-ko": "EN ↔ KO",
  "en-es": "EN ↔ ES",
  "ko-es": "KO ↔ ES",
};

function readPair(): LanguagePair {
  try {
    const v = localStorage.getItem(PAIR_STORAGE_KEY);
    if (v && LANGUAGE_PAIRS.includes(v as LanguagePair)) {
      return v as LanguagePair;
    }
  } catch {
    // ignore
  }
  return DEFAULT_PAIR;
}

async function fetchJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

function StatBox({
  label,
  value,
  variant,
}: {
  label: string;
  value: number;
  variant?: "highlight" | "amber";
}) {
  const valueClass =
    variant === "highlight"
      ? "text-2xl font-semibold text-accent"
      : variant === "amber"
        ? "text-2xl font-semibold text-warning"
        : "text-2xl font-semibold text-ink";
  return (
    <Card>
      <p className={valueClass}>{value}</p>
      <p className="mt-1 text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
      </p>
    </Card>
  );
}

export function VocabPageClient({ learnerId }: { learnerId: string }) {
  const [pair, setPair] = useState<LanguagePair>(DEFAULT_PAIR);
  const [dueCards, setDueCards] = useState<VocabCard[]>([]);
  const [stats, setStats] = useState<VocabStats | null>(null);
  const [topics, setTopics] = useState<TopicItem[]>([]);
  const [loaded, setLoaded] = useState(false);

  // Hydrate from localStorage + subscribe to pair changes from the
  // home-page modal (same event the LanguagePairControls dispatch).
  useEffect(() => {
    const sync = () => setPair(readPair());
    sync();
    window.addEventListener(PAIR_CHANGED_EVENT, sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener(PAIR_CHANGED_EVENT, sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      const q = `?pair=${encodeURIComponent(pair)}`;
      const [due, st, tp] = await Promise.all([
        fetchJSON<VocabCard[]>(`/learners/${learnerId}/vocab/due?limit=20&pair=${pair}`),
        fetchJSON<VocabStats>(`/learners/${learnerId}/vocab/stats${q}`),
        // Topics are not per-pair; load once. Pair changes won't refetch.
        topics.length === 0
          ? fetchJSON<TopicItem[]>(`/learners/${learnerId}/vocab/topics`)
          : Promise.resolve(topics),
      ]);
      if (cancelled) return;
      setDueCards(due ?? []);
      setStats(st);
      setTopics(tp ?? []);
      setLoaded(true);
    }
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pair, learnerId]);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-ink">Vocabulary deck</h2>
        <span
          className="font-mono text-xs text-ink-faint"
          aria-label="Current language pair"
        >
          {PAIR_LABEL[pair]}
        </span>
      </div>

      {stats && (
        <div className="grid grid-cols-4 gap-3">
          <StatBox label="Total cards" value={stats.total} />
          <StatBox label="Due now" value={stats.due_now} variant="highlight" />
          <StatBox
            label="Knowledge gaps"
            value={stats.knowledge_gaps}
            variant="amber"
          />
          <StatBox label="Memory gaps" value={stats.memory_gaps} />
        </div>
      )}

      <TopicSelector learnerId={learnerId} activeTopics={topics} />

      {!loaded ? (
        <p className="text-sm text-ink-faint">Loading…</p>
      ) : dueCards.length > 0 ? (
        <DeckView learnerId={learnerId} initialCards={dueCards} />
      ) : (
        <p className="text-sm text-ink-faint">
          No cards due for {PAIR_LABEL[pair]} right now. Switch pair on the
          home page, add a topic above, or come back later.
        </p>
      )}
    </div>
  );
}
