import type { ReactNode } from "react";
import { BackToHome } from "@/app/learner/[learnerId]/BackToHome";

export default async function VocabLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;
  return (
    <div className="mx-auto min-h-screen w-full max-w-2xl bg-zinc-950 p-8 text-zinc-100">
      <header className="mb-6 border-b border-zinc-800 pb-4">
        <div className="mb-3">
          <BackToHome learnerId={learnerId} />
        </div>
        <h1 className="text-2xl font-semibold">Vocabulary deck</h1>
        <p className="text-sm text-zinc-500">
          Spaced-repetition review. Terms are added from topics you study and
          from interpretation attempts where vocabulary was missed.
        </p>
      </header>
      {children}
    </div>
  );
}
