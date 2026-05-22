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
    <div className="rounded-xl bg-gradient-to-br from-emerald-900/60 to-emerald-700/30 border border-emerald-800/50 p-5">
      <p className="text-xs uppercase tracking-wide text-emerald-300/80">
        Day streak
      </p>
      <p className="mt-1 text-4xl font-bold text-emerald-100">{days}</p>
      <p className="mt-2 text-xs italic text-emerald-300/70">{flavor}</p>
    </div>
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
    <div className="rounded-xl bg-gradient-to-br from-amber-900/60 to-amber-700/30 border border-amber-800/50 p-5">
      <p className="text-xs uppercase tracking-wide text-amber-300/80">
        Minutes interpreted
      </p>
      <p className="mt-1 text-4xl font-bold text-amber-100">{minutes}</p>
      <p className="mt-2 text-xs italic text-amber-300/70">
        that&apos;s {flavor}
      </p>
    </div>
  );
}

function MasteryRow({ score }: { score: MasteryScore }) {
  const pct = Math.round(score.mastery * 100);
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-3">
      <div className="mb-1 flex items-center justify-between text-sm">
        <span className="font-medium capitalize">{score.domain}</span>
        <span className="text-zinc-400">
          {pct}% · {score.attempts_count} attempts
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
        <div className="h-full bg-emerald-600" style={{ width: `${pct}%` }} />
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
  return (
    <li className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
      <span className="capitalize">{session.domain}</span>
      <span className="text-xs text-zinc-500">{date}</span>
      <span className="text-zinc-300">{session.attempts_count} attempts</span>
      <span className="font-mono text-emerald-400">{score}</span>
    </li>
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
      {/* Compact greeting */}
      <section>
        <h2 className="text-2xl font-semibold">
          Welcome back{learner ? `, ${learner.display_name}` : ""}.
        </h2>
        <p className="mt-1 text-sm text-zinc-500">Pick up where you left off.</p>
      </section>

      {/* Feature grid — hero */}
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

      {/* Overview */}
      <section>
        <h3 className="mb-3 text-sm font-medium uppercase tracking-wide text-zinc-500">
          Overview
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <StreakTile days={overview?.streak_days ?? 0} />
          <MinutesTile seconds={overview?.total_seconds_interpreted ?? 0} />
        </div>

        <div className="mt-6">
          <p className="mb-2 text-xs uppercase tracking-wide text-zinc-500">
            Mastery by domain
          </p>
          {mastery.length === 0 ? (
            <p className="text-sm text-zinc-500">
              No attempts yet &mdash; let&apos;s change that.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {mastery.map((m) => (
                <MasteryRow key={m.domain} score={m} />
              ))}
            </div>
          )}
        </div>
      </section>

      {/* Recent sessions */}
      <section>
        <h3 className="mb-2 text-sm font-medium uppercase tracking-wide text-zinc-500">
          Recent sessions
        </h3>
        {sessionList.length === 0 ? (
          <p className="text-sm text-zinc-500">No sessions yet.</p>
        ) : (
          <ul className="flex flex-col divide-y divide-zinc-800 rounded-lg border border-zinc-800 bg-zinc-900">
            {sessionList.map((s) => (
              <SessionRow key={s.id} session={s} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
