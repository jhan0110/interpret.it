import { DeckView } from "./DeckView";
import { TopicSelector } from "./TopicSelector";

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

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

async function fetchDue(learnerId: string): Promise<VocabCard[]> {
  const res = await fetch(
    `${GATEWAY_URL}/learners/${learnerId}/vocab/due?limit=20`,
    { cache: "no-store" },
  );
  if (!res.ok) return [];
  return (await res.json()) as VocabCard[];
}

async function fetchStats(learnerId: string): Promise<VocabStats | null> {
  const res = await fetch(
    `${GATEWAY_URL}/learners/${learnerId}/vocab/stats`,
    { cache: "no-store" },
  );
  if (!res.ok) return null;
  return (await res.json()) as VocabStats;
}

async function fetchTopics(learnerId: string): Promise<TopicItem[]> {
  const res = await fetch(
    `${GATEWAY_URL}/learners/${learnerId}/vocab/topics`,
    { cache: "no-store" },
  );
  if (!res.ok) return [];
  return (await res.json()) as TopicItem[];
}

export default async function VocabPage({
  params,
}: {
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;
  const [dueCards, stats, topics] = await Promise.all([
    fetchDue(learnerId),
    fetchStats(learnerId),
    fetchTopics(learnerId),
  ]);

  return (
    <div className="flex flex-col gap-8">
      {stats && (
        <div className="grid grid-cols-4 gap-3">
          <StatBox label="Total cards" value={stats.total} />
          <StatBox label="Due now" value={stats.due_now} highlight />
          <StatBox label="Knowledge gaps" value={stats.knowledge_gaps} amber />
          <StatBox label="Memory gaps" value={stats.memory_gaps} blue />
        </div>
      )}

      <TopicSelector learnerId={learnerId} activeTopics={topics} />

      {dueCards.length > 0 ? (
        <DeckView learnerId={learnerId} initialCards={dueCards} />
      ) : (
        <p className="text-sm text-zinc-500">
          No cards due right now. Add a topic above or come back later.
        </p>
      )}
    </div>
  );
}

function StatBox({
  label,
  value,
  highlight,
  amber,
  blue,
}: {
  label: string;
  value: number;
  highlight?: boolean;
  amber?: boolean;
  blue?: boolean;
}) {
  const valueClass = highlight
    ? "text-emerald-400"
    : amber
      ? "text-amber-400"
      : blue
        ? "text-blue-400"
        : "text-zinc-100";
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
      <p className={`text-2xl font-semibold ${valueClass}`}>{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{label}</p>
    </div>
  );
}
