"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { tokens } from "@/lib/api";
import { SignalLogo } from "@/components/icons";

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(tokens.access ? "/chats" : "/login");
  }, [router]);

  return (
    <main className="flex h-dvh items-center justify-center bg-sig-bg">
      <SignalLogo size={44} className="animate-pulse text-ultramarine" />
    </main>
  );
}
