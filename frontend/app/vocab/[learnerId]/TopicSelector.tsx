"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { TopicItem } from "./page";

const GATEWAY_URL =
  process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

const ALL_DOMAINS = [
  { value: "logistics", label: "Logistics" },
  { value: "diplomacy", label: "Diplomacy" },
  { value: "intelligence", label: "Intelligence" },
  { value: "operations", label: "Operations" },
  { value: "medical", label: "Medical" },
  { value: "cyber", label: "Cyber" },
] as const;

export function TopicSelector({
  learnerId,
  activeTopics,
}: {
  learnerId: string;
  activeTopics: TopicItem[];
}) {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeDomains = new Set(activeTopics.map((t) => t.domain));

  async function addTopic(domain: string) {
    setLoading(domain);
    setError(null);
    try {
      const res = await fetch(
        `${GATEWAY_URL}/learners/${learnerId}/vocab/topics`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ domain }),
        },
      );
      if (!res.ok) {
        const text = await res.text();
        setError(`Failed to add topic: ${text}`);
        return;
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(null);
    }
  }

  async function removeTopic(domain: string) {
    setLoading(domain);
    setError(null);
    try {
      const res = await fetch(
        `${GATEWAY_URL}/learners/${learnerId}/vocab/topics/${domain}`,
        { method: "DELETE" },
      );
      if (!res.ok && res.status !== 204) {
        setError(`Failed to remove topic`);
        return;
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(null);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm font-medium text-zinc-400">Study topics</p>
      <div className="flex flex-wrap gap-2">
        {ALL_DOMAINS.map(({ value, label }) => {
          const active = activeDomains.has(value);
          const busy = loading === value;
          return (
            <button
              key={value}
              onClick={() => (active ? removeTopic(value) : addTopic(value))}
              disabled={busy}
              className={[
                "rounded-full px-3 py-1 text-xs font-medium transition-colors disabled:opacity-50",
                active
                  ? "bg-emerald-800 text-emerald-200 hover:bg-emerald-700"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200",
              ].join(" ")}
            >
              {busy ? "..." : active ? `${label} ✓` : label}
            </button>
          );
        })}
      </div>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
