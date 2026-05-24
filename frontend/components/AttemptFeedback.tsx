import type {
  KeyPoint,
  ProsodyResult,
  SemanticError,
  SemanticResult,
} from "@/lib/contracts";

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

type Props = {
  semanticResult: SemanticResult | null;
  prosodyResult: ProsodyResult | null;
  audioUrl?: string | null;
};

export function AttemptFeedback({ semanticResult, prosodyResult, audioUrl }: Props) {
  const isMemorization =
    semanticResult?.mode === "memorization" &&
    semanticResult.key_points !== null &&
    semanticResult.key_points.length > 0;

  return (
    <>
      {audioUrl != null && (
        <div className="mb-4">
          {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
          <audio src={audioUrl} controls preload="metadata" className="w-full" />
        </div>
      )}

      {semanticResult ? (
        <div className="space-y-3">
          {semanticResult.source_text && !isMemorization && (
            <div>
              <h3 className="text-sm font-semibold">Source</h3>
              <p className="text-sm text-zinc-800">
                {semanticResult.source_text}
              </p>
            </div>
          )}
          <div>
            <h3 className="text-sm font-semibold">
              {isMemorization ? "Your recall" : "Your interpretation"}
            </h3>
            <p className="text-sm text-zinc-800">
              {semanticResult.transcript || "(empty)"}
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold">
              {isMemorization ? "Source" : "Reference translation"}
            </h3>
            <p className="text-sm text-zinc-800">
              {semanticResult.reference_translation}
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold">Score</h3>
            <p className="text-sm">
              {(semanticResult.overall_score * 100).toFixed(0)}%
            </p>
          </div>
          {isMemorization ? (
            <KeyPointsGrid points={semanticResult.key_points ?? []} />
          ) : (
            semanticResult.errors.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold">Errors</h3>
                <ul className="space-y-2">
                  {semanticResult.errors.map((e, i) => (
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
            )
          )}
          <div>
            <h3 className="text-sm font-semibold">Feedback</h3>
            <p className="text-sm text-zinc-700">{semanticResult.feedback_text}</p>
          </div>
        </div>
      ) : (
        <p className="text-sm text-zinc-500">Awaiting semantic result.</p>
      )}

      {prosodyResult && (
        <div className="mt-4 rounded bg-zinc-50 p-2 text-xs text-zinc-600">
          Pauses {prosodyResult.pause_count} · Fillers {prosodyResult.filler_count}{" "}
          · WPM {prosodyResult.mean_wpm.toFixed(0)} · Cognitive load{" "}
          {prosodyResult.cognitive_load_estimate}
        </div>
      )}
    </>
  );
}

function KeyPointsGrid({ points }: { points: KeyPoint[] }) {
  return (
    <div>
      <h3 className="text-sm font-semibold">Key points</h3>
      <ul className="mt-1 space-y-1.5">
        {points.map((p, i) => (
          <KeyPointRow key={i} point={p} />
        ))}
      </ul>
    </div>
  );
}

function KeyPointRow({ point }: { point: KeyPoint }) {
  const isPrimary = point.importance === "primary";
  const indicatorColor = point.recalled ? "bg-emerald-500" : "bg-zinc-300";
  const indicatorChar = point.recalled ? "✓" : "·";
  const textWeight = isPrimary ? "font-semibold text-zinc-900" : "font-normal text-zinc-700";
  const textSize = isPrimary ? "text-sm" : "text-xs";

  return (
    <li className="flex items-start gap-2 rounded border border-zinc-200 bg-white p-2">
      <span
        aria-label={point.recalled ? "Recalled" : "Missed"}
        className={`mt-0.5 inline-flex h-4 w-4 flex-none items-center justify-center rounded-full text-[10px] text-white ${indicatorColor}`}
      >
        <span aria-hidden>{indicatorChar}</span>
      </span>
      <div className="flex-1">
        <p className={`${textSize} ${textWeight}`}>{point.text}</p>
        <span
          className={`mt-0.5 inline-block text-[10px] uppercase tracking-widest ${
            isPrimary ? "text-zinc-500" : "text-zinc-400"
          }`}
        >
          {isPrimary ? "Primary" : "Secondary"}
        </span>
      </div>
    </li>
  );
}
