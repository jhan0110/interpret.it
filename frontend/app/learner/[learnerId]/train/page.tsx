import { CreateSessionForm } from "@/app/CreateSessionForm";
import { BackToHome } from "../BackToHome";

export default async function TrainPage({
  params,
}: {
  params: Promise<{ learnerId: string }>;
}) {
  const { learnerId } = await params;
  return (
    <main className="flex flex-col gap-6">
      <BackToHome learnerId={learnerId} />
      <div>
        <h2 className="text-2xl font-semibold">Start a training session</h2>
        <p className="mt-1 text-sm text-zinc-500">
          Configure parameters for a generated 10-phrase session.
        </p>
      </div>
      <CreateSessionForm learnerId={learnerId} />
    </main>
  );
}
