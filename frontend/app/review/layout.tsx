import type { ReactNode } from "react";

export default function ReviewLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto min-h-screen w-full max-w-4xl p-8 text-ink">
      <header className="mb-6 border-b border-accent pb-4">
        <h1 className="text-2xl font-semibold">Session review</h1>
        <p className="text-sm text-ink-faint">
          Transcripts, references, and per-attempt feedback. This view is only
          accessible after a session completes.
        </p>
      </header>
      {children}
    </div>
  );
}
