import { Card } from "@/components/Card";
import { FEATURES } from "./features";
import { FeatureCard } from "./FeatureCard";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

async function safeFetch<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

interface MasteryScore {
  domain: string;
  mastery: number;
  attempts_count: number;
  last_attempt_at: string;
}

interface SessionSummary {
  id: string;
  domain: string;
  started_at: string;
  completed_at: string | null;
  state: string;
  attempts_count: number;
  mean_score: number | null;
}

function StreakTile({ days }: { days: number }) {
  const flavor =
    days === 0
      ? "Start today"
      : days < 3
        ? "Keep going"
        : days < 7
          ? "You're on a roll"
          : "On fire";
  return (
    <Card className="p-5">
      <p className="text-[10px] uppercase tracking-wide text-ink-faint">
        Day streak
      </p>
      <p className="mt-1 text-3xl font-bold text-ink">{days}</p>
      <p className="mt-2 text-sm text-ink-soft">{flavor}</p>
    </Card>
  );
}

function MinutesTile({ seconds }: { seconds: number }) {
  const minutes = Math.floor(seconds / 60);
  const flavor =
    minutes < 1
      ? "a deep breath"
      : minutes < 5
        ? "a song"
        : minutes < 15
          ? "a coffee break"
          : minutes < 30
            ? "a TV episode"
            : minutes < 60
              ? "a sitcom"
              : "a movie!";
  return (
    <Card className="p-5">
      <p className="text-[10px] uppercase tracking-wide text-ink-faint">
        Minutes interpreted
      </p>
      <p className="mt-1 text-3xl font-bold text-ink">{minutes}</p>
      <p className="mt-2 text-sm text-ink-soft">
        that&apos;s {flavor}
      </p>
    </Card>
  );
}

function MasteryRow({ score }: { score: MasteryScore }) {
  const pct = Math.round(score.mastery * 100);
  return (
    <div className="flex flex-col gap-1 border-b border-accent pb-2 last:border-0 last:pb-0">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium capitalize text-ink-soft">{score.domain}</span>
        <span className="text-ink-faint">
          {pct}% &middot; {score.attempts_count} attempts
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-[1px] bg-paper-tint">
        <div className="h-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function SessionRow({ session }: { session: SessionSummary }) {
  const date = new Date(session.started_at).toLocaleDateString();
  const score =
    session.mean_score !== null
      ? `${Math.round(session.mean_score * 100)}%`
      : "—";
  const hasScore = session.mean_score !== null;
  const scorePct = session.mean_score !== null ? session.mean_score : 0;
  const scoreBadge = hasScore
    ? scorePct >= 0.75
      ? "bg-accent text-paper px-2 py-0.5 text-xs rounded-[2px] font-mono"
      : "border border-ink-faint text-ink px-2 py-0.5 text-xs rounded-[2px] font-mono"
    : "text-ink-faint text-xs font-mono";
  return (
    <Card className="flex items-center justify-between gap-3 px-4 py-2">
      <span className="capitalize text-ink-soft text-sm">{session.domain}</span>
      <span className="text-xs text-ink-faint">{date}</span>
      <span className="text-sm text-ink-soft">{session.attempts_count} attempts</span>
      <span className={scoreBadge}>{score}</span>
    </Card>
  );
}

export default async function LearnerHome({
  params,
}: {
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;

  const [learner, vocab, masteryResp, sessions, overview] = await Promise.all([
    safeFetch<{ display_name: string; primary_lang: string }>(
      `${GATEWAY_URL}/learners/${learnerId}`,
    ),
    safeFetch<{
      total: number;
      due_now: number;
      knowledge_gaps: number;
      memory_gaps: number;
      by_domain: Record<string, number>;
    }>(`${GATEWAY_URL}/learners/${learnerId}/vocab/stats`),
    safeFetch<{
      scores: MasteryScore[];
    }>(`${GATEWAY_URL}/learners/${learnerId}/mastery`),
    safeFetch<SessionSummary[]>(
      `${GATEWAY_URL}/learners/${learnerId}/sessions?limit=5`,
    ),
    safeFetch<{
      learner_id: string;
      streak_days: number;
      total_seconds_interpreted: number;
      mastery_scores: MasteryScore[];
    }>(`${GATEWAY_URL}/learners/${learnerId}/overview`),
  ]);

  const mastery = overview?.mastery_scores ?? masteryResp?.scores ?? [];
  const sessionList = sessions ?? [];

  function getFeatureStatus(
    statusKey: "training" | "vocab" | null,
  ): { statusText: string; statusVariant: "neutral" | "highlight" } | undefined {
    if (statusKey === "vocab") {
      if (vocab !== null && vocab.due_now > 0) {
        return { statusText: `${vocab.due_now} cards due`, statusVariant: "highlight" };
      }
      return { statusText: `${vocab?.total ?? 0} total cards`, statusVariant: "neutral" };
    }
    if (statusKey === "training") {
      if (sessionList.length > 0) {
        const lastDate = new Date(sessionList[0].started_at).toLocaleDateString();
        const count = sessionList.length;
        return {
          statusText: `${count} session${count !== 1 ? "s" : ""} · last ${lastDate}`,
          statusVariant: "neutral",
        };
      }
      return { statusText: "No sessions yet", statusVariant: "neutral" };
    }
    return undefined;
  }

  return (
    <div className="flex flex-col gap-10">
      <section>
        <h2 className="text-2xl font-semibold text-ink">
          Welcome back{learner ? `, ${learner.display_name}` : ""}.
        </h2>
        <p className="mt-1 text-sm text-ink-soft">Pick up where you left off.</p>
      </section>

      <section>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {FEATURES.map((f) => {
            const badge = getFeatureStatus(f.statusKey);
            return (
              <FeatureCard
                key={f.id}
                feature={f}
                learnerId={learnerId}
                statusText={badge?.statusText}
                statusVariant={badge?.statusVariant}
              />
            );
          })}
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-[10px] font-medium uppercase tracking-wide text-ink-faint">
          Overview
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <StreakTile days={overview?.streak_days ?? 0} />
          <MinutesTile seconds={overview?.total_seconds_interpreted ?? 0} />
        </div>

        <div className="mt-6">
          <p className="mb-3 text-[10px] uppercase tracking-wide text-ink-faint">
            Mastery by domain
          </p>
          {mastery.length === 0 ? (
            <p className="text-sm text-ink-soft">
              No attempts yet &mdash; let&apos;s change that.
            </p>
          ) : (
            <div className="flex flex-col gap-3">
              {mastery.map((m) => (
                <MasteryRow key={m.domain} score={m} />
              ))}
            </div>
          )}
        </div>
      </section>

      <section>
        <h3 className="mb-2 text-[10px] font-medium uppercase tracking-wide text-ink-faint">
          Recent sessions
        </h3>
        {sessionList.length === 0 ? (
          <p className="text-sm text-ink-soft">No sessions yet.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {sessionList.map((s) => (
              <SessionRow key={s.id} session={s} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
