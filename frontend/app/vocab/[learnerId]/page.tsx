import { VocabPageClient } from "./VocabPageClient";

// Shared shapes used by VocabPageClient and DeckView.
export interface VocabCard {
  deck_id: string;
  entry_id: string;
  term: string;
  definition: string;
  domain: string;
  source_lang: string;
  target_lang: string;
  register: string;
  gap_type: "knowledge_gap" | "memory_gap" | null;
  added_by: string;
  next_review_at: string;
  interval_days: number;
  repetitions: number;
}

export interface VocabStats {
  total: number;
  due_now: number;
  knowledge_gaps: number;
  memory_gaps: number;
  by_domain: Record<string, number>;
}

export interface TopicItem {
  domain: string;
  added_at: string;
}

// The vocab page is fully client-rendered because the deck is keyed
// by the home-page language pair, which lives in localStorage. The
// page subscribes to the `interpretit:pair-changed` event so a pair
// switch in the home-page modal refreshes the deck in place.
export default async function VocabPage({
  params,
}: {
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;
  return <VocabPageClient learnerId={learnerId} />;
}
