import { CreateSessionForm } from "@/app/CreateSessionForm";
import { Card } from "@/components/Card";
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
        <h2 className="text-2xl font-semibold text-ink">Start a training session</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Configure parameters for a generated 10-phrase session.
        </p>
      </div>
      <Card className="p-6">
        <CreateSessionForm learnerId={learnerId} />
      </Card>
    </main>
  );
}
