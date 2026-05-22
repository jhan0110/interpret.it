"use client";

import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();
  return (
    <button
      onClick={() => {
        localStorage.removeItem("interpretit:learner_id");
        router.push("/login");
      }}
      className="rounded border border-zinc-700 px-3 py-1 text-xs text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
    >
      Logout
    </button>
  );
}
