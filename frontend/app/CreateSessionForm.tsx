"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type {
  GenerationParams,
  PostSessionRequest,
  PostSessionResponse,
  SessionMode,
} from "@/lib/contracts";
import { LanguageSwitch } from "@/components/LanguageSwitch";
import { DifficultySlider } from "@/components/DifficultySlider";
import { DirectionSwitch } from "@/components/DirectionSwitch";

const GATEWAY_URL =
  process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8000";

type Direction = "en-ko" | "ko-en";
type MonoLang = "en" | "ko";

const DIRECTIONS: Record<
  Direction,
  { source_lang: "en" | "ko"; target_lang: "en" | "ko"; label: string }
> = {
  "en-ko": { source_lang: "en", target_lang: "ko", label: "English → Korean" },
  "ko-en": { source_lang: "ko", target_lang: "en", label: "Korean → English" },
};

const MONO_LANGS: Record<MonoLang, string> = {
  en: "English",
  ko: "Korean",
};

const TOPICS = [
  { value: "logistics", label: "Logistics" },
  { value: "diplomacy", label: "Diplomacy" },
  { value: "intelligence", label: "Intelligence" },
  { value: "operations", label: "Operations" },
  { value: "medical", label: "Medical" },
  { value: "cyber", label: "Cyber" },
] as const;

const LEVELS = [
  { value: 1, label: "1 — Foundational" },
  { value: 2, label: "2 — Building" },
  { value: 3, label: "3 — Working" },
  { value: 4, label: "4 — Advanced" },
  { value: 5, label: "5 — Expert" },
] as const;

const DURATIONS = [
  { value: "short", label: "Short (~10s/phrase)" },
  { value: "medium", label: "Medium (~20s/phrase)" },
  { value: "long", label: "Long (~40s/phrase)" },
] as const;

export function CreateSessionForm({
  learnerId: presetLearnerId,
  mode = "interpretation",
  submitLabel,
  submittingLabel,
}: {
  learnerId?: string;
  mode?: SessionMode;
  submitLabel?: string;
  submittingLabel?: string;
} = {}) {
  const router = useRouter();
  const isMemorization = mode === "memorization";
  const [learnerId, setLearnerId] = useState(presetLearnerId ?? "");
  const [direction, setDirection] = useState<Direction>("en-ko");
  const [language, setLanguage] = useState<MonoLang>("en");
  const [topics, setTopics] = useState<string[]>(["logistics"]);
  const [userLevel, setUserLevel] =
    useState<GenerationParams["user_level"]>(3);
  const [duration, setDuration] =
    useState<GenerationParams["duration"]>("medium");
  const [currentContext, setCurrentContext] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function toggleTopic(value: string) {
    setTopics((prev) =>
      prev.includes(value)
        ? prev.filter((t) => t !== value)
        : [...prev, value],
    );
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (topics.length === 0) {
      setError("Pick at least one topic.");
      return;
    }
    setSubmitting(true);
    const { source_lang, target_lang } = isMemorization
      ? { source_lang: language, target_lang: language }
      : DIRECTIONS[direction];
    const body: PostSessionRequest = {
      learner_id: learnerId.trim(),
      domain: topics[0],
      source_lang,
      target_lang,
      mode,
      generation: {
        topics,
        user_level: userLevel,
        duration,
        current_context: currentContext.trim() || null,
      },
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
      {presetLearnerId === undefined && (
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
            className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-[#001b69] focus:outline-none"
          />
        </div>
      )}

      {isMemorization ? (
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium">Language</span>
          <LanguageSwitch value={language} onChange={setLanguage} />
          <p className="text-xs text-zinc-500">
            You will hear and recall in the same language.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium">Direction</span>
          <DirectionSwitch value={direction} onChange={setDirection} />
        </div>
      )}

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Topics</legend>
        <div className="grid grid-cols-3 gap-2" role="group" aria-label="Topics">
          {TOPICS.map((t) => {
            const selected = topics.includes(t.value);
            return (
              <button
                key={t.value}
                type="button"
                role="checkbox"
                aria-checked={selected}
                onClick={() => toggleTopic(t.value)}
                style={selected ? { background: "#001b69" } : undefined}
                className={`rounded-full border px-3 py-1.5 text-sm font-medium transition-colors ${
                  selected
                    ? "border-transparent text-white"
                    : "border-zinc-700 bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">Difficulty</span>
        <DifficultySlider
          value={userLevel}
          onChange={setUserLevel}
          options={LEVELS.map((l) => ({ value: l.value, label: l.label }))}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="duration" className="text-sm font-medium">
          Phrase length
        </label>
        <select
          id="duration"
          value={duration}
          onChange={(e) =>
            setDuration(e.target.value as GenerationParams["duration"])
          }
          required
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-[#001b69] focus:outline-none"
        >
          {DURATIONS.map((d) => (
            <option key={d.value} value={d.value}>
              {d.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="context" className="text-sm font-medium">
          Current context <span className="text-zinc-500">(optional)</span>
        </label>
        <textarea
          id="context"
          value={currentContext}
          onChange={(e) => setCurrentContext(e.target.value)}
          placeholder="e.g. NATO supply rerouting through Poland"
          rows={2}
          className="rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-[#001b69] focus:outline-none"
        />
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-400">
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        style={{ background: "#001b69" }}
        className="rounded px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {submitting
          ? (submittingLabel ?? "Generating...")
          : (submitLabel ?? "Start Session")}
      </button>
    </form>
  );
}
