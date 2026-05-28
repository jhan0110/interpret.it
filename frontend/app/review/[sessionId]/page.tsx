import Link from "next/link";
import { AttemptFeedback } from "@/components/AttemptFeedback";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
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

  const audioUrls = await Promise.all(
    attempts.map((a) => fetchAttemptAudioUrl(sessionId, a.id))
  );

  const learnerId = summary?.session.learner_id ?? null;

  return (
    <div className="space-y-8">
      <nav className="flex items-center justify-between border-b border-accent pb-3">
        <Link
          href={learnerId ? `/learner/${learnerId}` : "/"}
          className="inline-flex items-center gap-1 text-sm text-accent hover:underline underline-offset-2"
        >
          <span aria-hidden>←</span>
          <span>Home</span>
        </Link>
        {learnerId && (
          <Link href={`/learner/${learnerId}/train`}>
            <Button variant="primary">Start another session</Button>
          </Link>
        )}
      </nav>

      {summary && (
        <Card as="section">
          <h2 className="text-lg font-medium text-ink">Summary</h2>
          <p className="text-sm text-ink-soft">
            {summary.attempts_count} attempt(s) — mean score{" "}
            {(summary.mean_score * 100).toFixed(0)}%
          </p>
        </Card>
      )}

      <section className="space-y-6">
        {attempts.length === 0 && (
          <p className="text-sm text-ink-faint">No attempts recorded.</p>
        )}
        {attempts.map((a, idx) => (
          <Card key={a.id} as="article">
            <header className="mb-3 flex items-baseline justify-between">
              <span className="text-xs uppercase tracking-widest text-ink-faint">
                Attempt
              </span>
              <span className="font-mono text-xs text-ink-faint">{a.id}</span>
            </header>

            <AttemptFeedback
              semanticResult={a.semantic_result}
              prosodyResult={a.prosody_result}
              audioUrl={audioUrls[idx]}
            />
          </Card>
        ))}
      </section>
    </div>
  );
}
