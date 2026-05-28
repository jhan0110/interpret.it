import type {
  KeyPoint,
  ProsodyResult,
  SemanticError,
  SemanticResult,
} from "@/lib/contracts";

function severityColor(severity: SemanticError["severity"]): string {
  switch (severity) {
    case "minor":
      return "border-l-4 border-ink-faint pl-3";
    case "moderate":
      return "border-l-4 border-warning pl-3";
    case "critical":
      return "border-l-4 border-critical pl-3";
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
              <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">Source</h3>
              <p className="text-sm text-ink">
                {semanticResult.source_text}
              </p>
            </div>
          )}
          <div>
            <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">
              {isMemorization ? "Your recall" : "Your interpretation"}
            </h3>
            <p className="text-sm text-ink">
              {semanticResult.transcript || "(empty)"}
            </p>
          </div>
          <div>
            <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">
              {isMemorization ? "Source" : "Reference translation"}
            </h3>
            <p className="text-sm text-ink">
              {semanticResult.reference_translation}
            </p>
          </div>
          <div>
            <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">Score</h3>
            <p className="text-sm">
              {(semanticResult.overall_score * 100).toFixed(0)}%
            </p>
          </div>
          {isMemorization ? (
            <KeyPointsGrid points={semanticResult.key_points ?? []} />
          ) : (
            semanticResult.errors.length > 0 && (
              <div>
                <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">Errors</h3>
                <ul className="space-y-2">
                  {semanticResult.errors.map((e, i) => (
                    <li
                      key={i}
                      className={`rounded-[2px] p-2 text-sm ${severityColor(e.severity)}`}
                    >
                      <div className="font-medium text-ink">{e.type}</div>
                      <div className="text-ink-soft">{e.explanation}</div>
                    </li>
                  ))}
                </ul>
              </div>
            )
          )}
          <div>
            <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">Feedback</h3>
            <p className="text-sm text-ink">{semanticResult.feedback_text}</p>
          </div>
        </div>
      ) : (
        <p className="text-sm text-ink-faint">Awaiting semantic result.</p>
      )}

      {prosodyResult && (
        <div className="mt-4 bg-paper-tint text-ink-soft border border-ink-faint rounded-[2px] p-2 text-xs">
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
      <h3 className="text-[10px] uppercase tracking-[0.15em] text-ink-faint font-semibold">Key points</h3>
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
  const textWeight = isPrimary ? "font-semibold text-ink" : "font-normal text-ink-soft";
  const textSize = isPrimary ? "text-sm" : "text-xs";

  return (
    <li className="flex items-start gap-2 rounded-[2px] border border-ink-faint p-2">
      <span
        aria-label={point.recalled ? "Recalled" : "Missed"}
        className={[
          "mt-0.5 inline-flex h-4 w-4 flex-none items-center justify-center text-[10px]",
          point.recalled
            ? "bg-accent text-paper"
            : "bg-transparent border border-ink-faint text-ink-faint",
        ].join(" ")}
      >
        <span aria-hidden>{point.recalled ? "✓" : "·"}</span>
      </span>
      <div className="flex-1">
        <p className={`${textSize} ${textWeight}`}>{point.text}</p>
        <span
          className={`mt-0.5 inline-block text-[10px] uppercase tracking-widest ${
            isPrimary ? "text-ink-faint" : "text-ink-faint"
          }`}
        >
          {isPrimary ? "Primary" : "Secondary"}
        </span>
      </div>
    </li>
  );
}
