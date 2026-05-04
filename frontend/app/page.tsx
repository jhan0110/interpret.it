export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-8">
      <h1 className="text-3xl font-semibold">Interpretit</h1>
      <p className="text-zinc-600">
        Real-time interpretation training. Begin a session from the operator
        dashboard, then navigate to /[sessionId] (audio-only mode) or
        /review/[sessionId] after completion.
      </p>
      <p className="text-xs text-zinc-400">
        The session route group renders no text — all transcripts and feedback
        prose are gated behind session completion in the review route.
      </p>
    </main>
  );
}
