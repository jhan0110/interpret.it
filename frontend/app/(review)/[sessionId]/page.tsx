import type {
  Attempt,
  CompleteSessionResponse,
  SemanticError,
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

function severityColor(severity: SemanticError["severity"]): string {
  switch (severity) {
    case "minor":
      return "border-zinc-300 bg-zinc-50";
    case "moderate":
      return "border-yellow-400 bg-yellow-50";
    case "critical":
      return "border-red-500 bg-red-50";
  }
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

  return (
    <div className="space-y-8">
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
        {attempts.map((a) => (
          <article key={a.id} className="rounded-md border border-zinc-200 p-4">
            <header className="mb-3 flex items-baseline justify-between">
              <span className="text-xs uppercase tracking-widest text-zinc-500">
                Attempt
              </span>
              <span className="font-mono text-xs text-zinc-400">{a.id}</span>
            </header>

            {a.semantic_result ? (
              <div className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold">Your interpretation</h3>
                  <p className="text-sm text-zinc-800">
                    {a.semantic_result.transcript || "(empty)"}
                  </p>
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Reference</h3>
                  <p className="text-sm text-zinc-800">
                    {a.semantic_result.reference_translation}
                  </p>
                </div>
                <div>
                  <h3 className="text-sm font-semibold">Score</h3>
                  <p className="text-sm">
                    {(a.semantic_result.overall_score * 100).toFixed(0)}%
                  </p>
                </div>
                {a.semantic_result.errors.length > 0 && (
                  <div>
                    <h3 className="text-sm font-semibold">Errors</h3>
                    <ul className="space-y-2">
                      {a.semantic_result.errors.map((e, i) => (
                        <li
                          key={i}
                          className={`rounded border p-2 text-sm ${severityColor(e.severity)}`}
                        >
                          <div className="font-medium">{e.type}</div>
                          <div className="text-zinc-700">{e.explanation}</div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <div>
                  <h3 className="text-sm font-semibold">Feedback</h3>
                  <p className="text-sm text-zinc-700">
                    {a.semantic_result.feedback_text}
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-zinc-500">Awaiting semantic result.</p>
            )}

            {a.prosody_result && (
              <div className="mt-4 rounded bg-zinc-50 p-2 text-xs text-zinc-600">
                Pauses {a.prosody_result.pause_count} · Fillers{" "}
                {a.prosody_result.filler_count} · WPM{" "}
                {a.prosody_result.mean_wpm.toFixed(0)} · Cognitive load{" "}
                {a.prosody_result.cognitive_load_estimate}
              </div>
            )}
          </article>
        ))}
      </section>
    </div>
  );
}
