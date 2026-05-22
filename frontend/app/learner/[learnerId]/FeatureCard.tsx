import Link from "next/link";
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
      ? "bg-emerald-900/40 text-emerald-300 rounded-full px-2 py-0.5 text-xs font-medium"
      : "bg-zinc-800 text-zinc-300 rounded-full px-2 py-0.5 text-xs font-medium";

  const body = (
    <>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-lg font-semibold text-zinc-100">{feature.title}</h3>
        {!available ? (
          <span className="rounded-full bg-zinc-800 px-2 py-0.5 text-xs text-zinc-400">
            Coming soon
          </span>
        ) : statusText !== undefined ? (
          <span className={badgeClass}>{statusText}</span>
        ) : null}
      </div>
      <p className="mt-2 text-sm text-zinc-400">{feature.description}</p>
    </>
  );

  if (!available) {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 opacity-60">
        {body}
      </div>
    );
  }

  return (
    <Link
      href={href!}
      className="block rounded-xl border border-zinc-800 bg-zinc-900 p-5 transition-colors hover:border-emerald-700 hover:bg-zinc-900/80"
    >
      {body}
      <p className="mt-3 text-xs text-emerald-400">Open →</p>
    </Link>
  );
}
