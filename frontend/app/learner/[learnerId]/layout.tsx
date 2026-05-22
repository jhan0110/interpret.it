import type { ReactNode } from "react";
import { LogoutButton } from "./LogoutButton";

export default function LearnerLayout({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto min-h-screen w-full max-w-3xl bg-zinc-950 p-8 text-zinc-100">
      <header className="mb-6 flex items-center justify-between border-b border-zinc-800 pb-4">
        <h1 className="text-xl font-semibold">Interpretit</h1>
        <LogoutButton />
      </header>
      {children}
    </div>
  );
}
