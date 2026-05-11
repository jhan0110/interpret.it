"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PostSessionResponse } from "@/lib/contracts";

const GATEWAY_URL =
  process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

interface CreateSessionBody {
  learner_id: string;
  domain: string;
  difficulty_level: number;
}

export function CreateSessionForm() {
  const router = useRouter();
  const [learnerId, setLearnerId] = useState("");
  const [domain, setDomain] = useState("");
  const [difficultyLevel, setDifficultyLevel] = useState(5);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    const body: CreateSessionBody = {
      learner_id: learnerId.trim(),
      domain: domain.trim(),
      difficulty_level: difficultyLevel,
    };

    try {
      const res = await fetch(`${GATEWAY_URL}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const text = await res.text();
        setError(`Request failed (${res.status}): ${text}`);
        return;
      }

      const session = (await res.json()) as PostSessionResponse;
      router.push(`/${session.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setSubmitting(false);
    }
  }

  return (
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
          pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
          required
          className="rounded border border-zinc-300 px-3 py-2 font-mono text-sm focus:border-zinc-500 focus:outline-none"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="domain" className="text-sm font-medium">
          Domain
        </label>
        <input
          id="domain"
          type="text"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="logistics, diplomacy, ..."
          required
          className="rounded border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-500 focus:outline-none"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="difficulty" className="text-sm font-medium">
          Difficulty level (1–10)
        </label>
        <input
          id="difficulty"
          type="number"
          min={1}
          max={10}
          value={difficultyLevel}
          onChange={(e) => setDifficultyLevel(Number(e.target.value))}
          required
          className="rounded border border-zinc-300 px-3 py-2 text-sm focus:border-zinc-500 focus:outline-none"
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
        {submitting ? "Starting..." : "Start Session"}
      </button>
    </form>
  );
}
