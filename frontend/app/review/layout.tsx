import type { ReactNode } from "react";
import Image from "next/image";

export default function ReviewLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto min-h-screen w-full max-w-4xl p-8 text-ink">
      <header className="mb-6 border-b border-accent pb-4">
        <div className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt=""
            width={28}
            height={28}
            priority
            className="rounded-[2px]"
          />
          <h1 className="text-2xl font-semibold">Session review</h1>
        </div>
        <p className="mt-1 text-sm text-ink-faint">
          Transcripts, references, and per-attempt feedback. This view is only
          accessible after a session completes.
        </p>
      </header>
      {children}
    </div>
  );
}
