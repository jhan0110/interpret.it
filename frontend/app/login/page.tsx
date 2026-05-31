"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Field, TextInput } from "@/components/Field";

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "";

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
      <div className="flex flex-col items-center gap-3 text-center">
        <Image
          src="/logo.png"
          alt=""
          width={80}
          height={80}
          priority
          className="rounded-[4px]"
        />
        <div>
          <h1 className="text-2xl font-semibold text-ink">interpretIt</h1>
          <p className="mt-1 text-sm text-ink-soft">
            Enter your learner ID to continue.
          </p>
        </div>
      </div>

      <Card className="p-6">
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <Field label="Learner ID" htmlFor="learner-id">
            <TextInput
              id="learner-id"
              type="text"
              value={learnerId}
              onChange={(e) => setLearnerId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              required
              autoFocus
            />
          </Field>

          {error && (
            <p role="alert" className="text-sm text-critical">
              {error}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Checking..." : "Continue"}
          </Button>

          <Button
            type="button"
            variant="ghost"
            onClick={() => setLearnerId(DEV_LEARNER_ID)}
          >
            Use dev learner
          </Button>
        </form>
      </Card>
    </main>
  );
}
