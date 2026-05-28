import Link from "next/link";

export function BackToHome({ learnerId }: { learnerId: string }) {
  return (
    <Link
      href={`/learner/${learnerId}`}
      className="inline-flex items-center gap-1 text-sm text-accent hover:text-accent-strong"
      aria-label="Back to home"
    >
      <span aria-hidden>←</span>
      <span>Home</span>
    </Link>
  );
}
