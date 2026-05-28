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
import { Field, TextInput, TextArea } from "@/components/Field";
import { SegmentedControl } from "@/components/SegmentedControl";
import { Button } from "@/components/Button";

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

const DURATION_OPTIONS = [
  { value: "short" as const, label: "Short" },
  { value: "medium" as const, label: "Medium" },
  { value: "long" as const, label: "Long" },
];

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
        <Field label="Learner ID" htmlFor="learner-id">
          <TextInput
            id="learner-id"
            type="text"
            value={learnerId}
            onChange={(e) => setLearnerId(e.target.value)}
            placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
            pattern="[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
            required
          />
        </Field>
      )}

      {isMemorization ? (
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-ink">Language</span>
          <LanguageSwitch value={language} onChange={setLanguage} />
          <p className="text-xs text-ink-faint">
            You will hear and recall in the same language.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-ink">Direction</span>
          <DirectionSwitch value={direction} onChange={setDirection} />
        </div>
      )}

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Topics</legend>
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
                className={`border rounded-[2px] px-3 py-1.5 text-sm font-medium transition-[background-color,border-color,color] duration-[120ms] ease-linear ${
                  selected
                    ? "bg-accent text-paper border-accent"
                    : "border-ink-faint text-ink hover:bg-accent-wash"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </fieldset>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium text-ink">Difficulty</span>
        <DifficultySlider
          value={userLevel}
          onChange={setUserLevel}
          options={LEVELS.map((l) => ({ value: l.value, label: l.label }))}
        />
      </div>

      <div className="flex flex-col gap-1">
        <span className="text-sm font-medium text-ink">Phrase length</span>
        <SegmentedControl
          value={duration}
          onChange={(next) => setDuration(next as GenerationParams["duration"])}
          options={DURATION_OPTIONS}
        />
        <p className="text-xs text-ink-faint">~10s / ~20s / ~40s per phrase</p>
      </div>

      <Field label="Current context" htmlFor="context" hint="(optional)">
        <TextArea
          id="context"
          value={currentContext}
          onChange={(e) => setCurrentContext(e.target.value)}
          placeholder="e.g. NATO supply rerouting through Poland"
          rows={2}
        />
      </Field>

      {error && (
        <p role="alert" className="text-sm text-warning">
          {error}
        </p>
      )}

      <Button variant="primary" type="submit" disabled={submitting}>
        {submitting
          ? (submittingLabel ?? "Generating...")
          : (submitLabel ?? "Start Session")}
      </Button>
    </form>
  );
}
