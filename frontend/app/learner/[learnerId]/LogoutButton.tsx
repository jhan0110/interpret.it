"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";

export function LogoutButton() {
  const router = useRouter();
  return (
    <Button
      variant="ghost"
      onClick={() => {
        localStorage.removeItem("interpretit:learner_id");
        router.push("/login");
      }}
    >
      Sign out
    </Button>
  );
}
