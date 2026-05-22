import type { ProsodyResult, SemanticError, SemanticResult } from "@/lib/contracts";

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

/**
 * Review-style breakdown of a single attempt — transcript, reference,
 * score, errors, prosody. Shared by the post-session review route and the
 * in-session feedback state. Light-themed; render on a light background.
 */
export function AttemptFeedback({ semanticResult, prosodyResult, audioUrl }: Props) {
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
          <div>
            <h3 className="text-sm font-semibold">Your interpretation</h3>
            <p className="text-sm text-zinc-800">
              {semanticResult.transcript || "(empty)"}
            </p>
          </div>
          <div>
            <h3 className="text-sm font-semibold">Reference</h3>
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
          {semanticResult.errors.length > 0 && (
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
