import { notFound } from "next/navigation";
import type { GetSessionResponse } from "@/lib/contracts";
import { SessionRunner } from "../SessionRunner";
import { MemorizationRunner } from "../MemorizationRunner";

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:8000";

async function fetchSession(
  sessionId: string,
): Promise<GetSessionResponse | null> {
  const res = await fetch(`${GATEWAY_URL}/sessions/${sessionId}`, {
    cache: "no-store",
  });
  if (!res.ok) return null;
  return (await res.json()) as GetSessionResponse;
}

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  const session = await fetchSession(sessionId);
  if (!session) {
    notFound();
  }
  if (session.mode === "memorization") {
    return (
      <MemorizationRunner
        sessionId={sessionId}
        replaysBudget={session.replays_budget}
      />
    );
  }
  return <SessionRunner sessionId={sessionId} />;
}
