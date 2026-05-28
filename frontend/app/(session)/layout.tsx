import type { ReactNode } from "react";

export default function SessionLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center text-ink">
      {children}
    </div>
  );
}
