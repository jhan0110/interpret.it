import { SessionRunner } from "../SessionRunner";

const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_BASE_URL ?? "ws://localhost:8000";

export default async function SessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = await params;
  return <SessionRunner sessionId={sessionId} wsBaseUrl={WS_BASE_URL} />;
}
