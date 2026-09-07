"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useConversationShell } from "@/lib/conversation-context";
import { useStore } from "@/lib/store";
import { ChatPane } from "@/components/ChatPane";
import { SignalLogo } from "@/components/icons";

export default function ConversationPage() {
  const router = useRouter();
  const { id } = useParams<{ id: string }>();
  const { openInfo } = useConversationShell();

  const booted = useStore((state) => state.booted);
  const conversations = useStore((state) => state.conversations);
  const openConversation = useStore((state) => state.openConversation);
  const upsertConversation = useStore((state) => state.upsertConversation);

  const conversation = conversations.find((c) => c.id === id) ?? null;

  useEffect(() => {
    if (!id || !booted) return;
    void openConversation(id);
  }, [id, booted, openConversation]);

  // Deep link into a conversation that is not in the loaded page yet.
  useEffect(() => {
    if (!booted || conversation || !id) return;
    let cancelled = false;
    api
      .conversation(id)
      .then((fresh) => !cancelled && upsertConversation(fresh))
      .catch(() => router.replace("/chats"));
    return () => {
      cancelled = true;
    };
  }, [booted, conversation, id, router, upsertConversation]);

  if (!conversation) {
    return (
      <section className="sig-canvas flex h-full flex-1 items-center justify-center">
        <SignalLogo size={36} className="animate-pulse text-sig-border" />
      </section>
    );
  }

  return <ChatPane conversation={conversation} onOpenInfo={openInfo} />;
}
