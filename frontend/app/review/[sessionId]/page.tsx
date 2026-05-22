import Link from "next/link";
import { AttemptFeedback } from "@/components/AttemptFeedback";
import type {
  Attempt,
  CompleteSessionResponse,
  GetAttemptAudioUrlResponse,
} from "@/lib/contracts";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

async function fetchAttempts(sessionId: string): Promise<Attempt[]> {
  const res = await fetch(`${GATEWAY_URL}/sessions/${sessionId}/attempts`, {
    cache: "no-store",
  });
  if (!res.ok) return [];
  return (await res.json()) as Attempt[];
}

async function fetchSummary(
  sessionId: string
): Promise<CompleteSessionResponse | null> {
  const res = await fetch(`${GATEWAY_URL}/sessions/${sessionId}/summary`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as CompleteSessionResponse;
}

async function fetchAttemptAudioUrl(
  sessionId: string,
  attemptId: string
): Promise<string | null> {
  const res = await fetch(
    `${GATEWAY_URL}/sessions/${sessionId}/attempts/${attemptId}/audio_url`,
    { cache: "no-store" }
  );
  if (!res.ok) return null;
  const data = (await res.json()) as GetAttemptAudioUrlResponse;
  return data.audio_url;
}

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  const [attempts, summary] = await Promise.all([
    fetchAttempts(sessionId),
    fetchSummary(sessionId),
  ]);

  // Fetch audio URLs for each attempt in parallel; missing/errored → null.
  const audioUrls = await Promise.all(
    attempts.map((a) => fetchAttemptAudioUrl(sessionId, a.id))
  );

  const learnerId = summary?.session.learner_id ?? null;

  return (
    <div className="space-y-8">
      <nav className="flex items-center justify-between border-b border-zinc-200 pb-3">
        <Link
          href={learnerId ? `/learner/${learnerId}` : "/"}
          className="inline-flex items-center gap-1 text-sm text-zinc-600 hover:text-zinc-900"
        >
          <span aria-hidden>←</span>
          <span>Home</span>
        </Link>
        {learnerId && (
          <Link
            href={`/learner/${learnerId}/train`}
            className="rounded bg-zinc-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-zinc-700"
          >
            Start another session
          </Link>
        )}
      </nav>

      {summary && (
        <section className="rounded-md border border-zinc-200 bg-zinc-50 p-4">
          <h2 className="text-lg font-medium">Summary</h2>
          <p className="text-sm text-zinc-600">
            {summary.attempts_count} attempt(s) — mean score{" "}
            {(summary.mean_score * 100).toFixed(0)}%
          </p>
        </section>
      )}

      <section className="space-y-6">
        {attempts.length === 0 && (
          <p className="text-sm text-zinc-500">No attempts recorded.</p>
        )}
        {attempts.map((a, idx) => (
          <article key={a.id} className="rounded-md border border-zinc-200 p-4">
            <header className="mb-3 flex items-baseline justify-between">
              <span className="text-xs uppercase tracking-widest text-zinc-500">
                Attempt
              </span>
              <span className="font-mono text-xs text-zinc-400">{a.id}</span>
            </header>

            <AttemptFeedback
              semanticResult={a.semantic_result}
              prosodyResult={a.prosody_result}
              audioUrl={audioUrls[idx]}
            />
          </article>
        ))}
      </section>
    </div>
  );
}
