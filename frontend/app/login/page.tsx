"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const GATEWAY_URL =
  process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const DEV_LEARNER_ID = "00000000-0000-0000-0000-000000000001";

export default function LoginPage() {
  const router = useRouter();
  const [learnerId, setLearnerId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const id = learnerId.trim();
    if (!UUID_RE.test(id)) {
      setError("Learner ID must be a UUID.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${GATEWAY_URL}/learners/${id}`);
      if (res.status === 404) {
        setError("Learner not found.");
        return;
      }
      if (!res.ok) {
        setError(`Request failed (${res.status})`);
        return;
      }
      localStorage.setItem("interpretit:learner_id", id);
      router.push(`/learner/${id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-8">
      <div>
        <h1 className="text-2xl font-semibold">Interpretit</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Enter your learner ID to continue.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <label htmlFor="learner-id" className="text-sm font-medium">
            Learner ID
          </label>
          <input
            id="learner-id"
            type="text"
            value={learnerId}
            onChange={(e) => setLearnerId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            required
            autoFocus
            className="rounded border border-zinc-300 px-3 py-2 font-mono text-sm focus:border-zinc-500 focus:outline-none"
          />
        </div>

        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submitting ? "Checking..." : "Continue"}
        </button>

        <button
          type="button"
          onClick={() => setLearnerId(DEV_LEARNER_ID)}
          className="text-center text-xs text-zinc-500 underline underline-offset-2 hover:text-zinc-700"
        >
          Use dev learner
        </button>
      </form>
    </main>
  );
}
