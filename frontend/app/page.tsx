"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

const UUID_RE =
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

export default function RootRedirect() {
  const router = useRouter();
  useEffect(() => {
    const id =
      typeof window !== "undefined"
        ? localStorage.getItem("interpretit:learner_id")
        : null;
    if (id && UUID_RE.test(id)) {
      router.replace(`/learner/${id}`);
    } else {
      router.replace("/login");
    }
  }, [router]);
  return null;
}
