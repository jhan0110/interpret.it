import type { ReactNode } from "react";
import Image from "next/image";
import { LogoutButton } from "./LogoutButton";

export default function LearnerLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto min-h-screen w-full max-w-3xl p-8">
      <header className="mb-6 flex items-center justify-between border-b border-accent pb-4">
        <div className="flex items-center gap-3">
          <Image
            src="/logo.png"
            alt=""
            width={32}
            height={32}
            priority
            className="rounded-[2px]"
          />
          <h1 className="text-xl font-semibold text-ink">Interpretit</h1>
        </div>
        <LogoutButton />
      </header>
      {children}
    </div>
  );
}
