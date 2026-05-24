import { CreateSessionForm } from "@/app/CreateSessionForm";
import { BackToHome } from "../BackToHome";

export default async function MemorizePage({
  params,
}: {
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;
  return (
    <main className="flex flex-col gap-6">
      <BackToHome learnerId={learnerId} />
      <div>
        <h2 className="text-2xl font-semibold">Memorization Practice</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Hear a phrase, then recall the key points from memory — all in the
          same language. No interpretation, just listening and recall.
        </p>
      </div>
      <CreateSessionForm
        learnerId={learnerId}
        mode="memorization"
        submitLabel="Start memorization session"
        submittingLabel="Generating..."
      />
    </main>
  );
}
