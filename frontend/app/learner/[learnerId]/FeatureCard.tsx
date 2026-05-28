import Link from "next/link";
import { Card } from "@/components/Card";
import type { Feature } from "./features";

export function FeatureCard({
  feature,
  learnerId,
  statusText,
  statusVariant,
}: {
  feature: Feature;
  learnerId: string;
  statusText?: string;
  statusVariant?: "neutral" | "highlight";
}) {
  const href = feature.href(learnerId);
  const available = feature.status === "available" && href !== null;

  const badgeClass =
    statusVariant === "highlight"
      ? "bg-accent text-paper inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded-[2px]"
      : "border border-ink-faint text-ink-faint inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider rounded-[2px]";

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-lg font-semibold text-ink">{feature.title}</h3>
        {!available ? (
          <span className="inline-block px-2 py-0.5 text-[10px] uppercase tracking-wider border border-ink-faint text-ink-faint rounded-[2px]">
            Coming soon
          </span>
        ) : statusText !== undefined ? (
          <span className={badgeClass}>{statusText}</span>
        ) : null}
      </div>
      <p className="mt-2 text-sm text-ink-soft">{feature.description}</p>
    </>
  );

  if (!available) {
    return (
      <Card className="opacity-60">
        {body}
      </Card>
    );
  }

  return (
    <Card interactive as="div" className="p-5">
      <Link href={href!} className="block">
        {body}
        <p className="mt-3 text-sm font-medium text-accent">Open →</p>
      </Link>
    </Card>
  );
}
