"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Conversation, Message } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { Modal, PrimaryButton } from "@/components/Modal";
import { CheckIcon, SearchIcon } from "@/components/icons";

function titleOf(conversation: Conversation): string {
  return conversation.name ?? conversation.peer?.display_name ?? "Unknown";
}

/** WhatsApp's "Forward to…" sheet: pick any number of chats, send a copy to each. */
export function ForwardModal({
  message,
  onClose,
}: {
  message: Message | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const conversations = useStore((state) => state.conversations);
  const toast = useStore((state) => state.toast);

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!message) return;
    setQuery("");
    setSelected([]);
  }, [message]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return conversations;
    return conversations.filter((c) => titleOf(c).toLowerCase().includes(needle));
  }, [conversations, query]);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function forward() {
    if (!message || selected.length === 0) return;
    setBusy(true);
    // Deliberately POSTed rather than routed through store.sendMessage: that
    // helper seeds an optimistic thread, and a one-message thread on a
    // conversation the user has never opened would stop openConversation from
    // ever fetching its real history. The server's own message.new broadcast
    // updates the list and any loaded thread for us.
    const results = await Promise.allSettled(
      selected.map((conversationId) =>
        api.sendMessage(conversationId, {
          content: message.content ?? "",
          client_msg_id: crypto.randomUUID(),
          type: message.type,
          attachments: message.attachments,
        }),
      ),
    );
    setBusy(false);

    const sent = results.filter((r) => r.status === "fulfilled").length;
    const failed = results.length - sent;
    if (sent > 0) toast(`Forwarded to ${sent} chat${sent === 1 ? "" : "s"}`);
    if (failed > 0) {
      toast(`${failed} chat${failed === 1 ? "" : "s"} could not be reached`, "error");
    }

    onClose();
    // Forwarding to exactly one chat reads as "go there", the way WhatsApp does.
    if (sent === 1 && failed === 0) router.push(`/chats/${selected[0]}`);
  }

  const preview = message?.content?.trim()
    ? message.content
    : message?.attachments.length
      ? `${message.attachments.length} attachment${message.attachments.length === 1 ? "" : "s"}`
      : "";

  return (
    <Modal
      open={message !== null}
      title="Forward to…"
      onClose={onClose}
      footer={
        <div className="flex items-center justify-between gap-2">
          <span className="pl-1 text-[13px] text-sig-text-3">
            {selected.length ? `${selected.length} selected` : "Pick a chat"}
          </span>
          <div className="flex gap-2">
            <PrimaryButton tone="ghost" onClick={onClose}>
              Cancel
            </PrimaryButton>
            <PrimaryButton disabled={busy || selected.length === 0} onClick={() => void forward()}>
              {busy ? "Sending…" : "Send"}
            </PrimaryButton>
          </div>
        </div>
      }
    >
      {preview && (
        <p
          className="mb-3 truncate rounded-lg px-3 py-2 text-[13.5px] text-sig-text-2"
          style={{ background: "var(--sig-hover)" }}
        >
          {preview}
        </p>
      )}

      <div className="relative mb-3">
        <SearchIcon
          size={16}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sig-text-3"
        />
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search chats"
          className="focus-ring w-full rounded-full bg-sig-input py-2.5 pl-9 pr-3 text-[14px] text-sig-text placeholder:text-sig-text-3"
        />
      </div>

      <div className="max-h-[46vh] overflow-y-auto pb-1">
        {matches.length === 0 ? (
          <p className="px-2 py-6 text-center text-[13.5px] text-sig-text-3">
            No chats match that
          </p>
        ) : (
          matches.map((conversation) => {
            const checked = selected.includes(conversation.id);
            return (
              <button
                key={conversation.id}
                onClick={() => toggle(conversation.id)}
                aria-pressed={checked}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-sig-hover"
              >
                <Avatar
                  name={titleOf(conversation)}
                  src={conversation.avatar_url ?? conversation.peer?.avatar_url ?? null}
                  seed={conversation.peer?.id ?? conversation.id}
                  size={40}
                  online={conversation.is_online}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[15px] text-sig-text">
                    {titleOf(conversation)}
                  </span>
                  {conversation.type === "group" && (
                    <span className="block truncate text-[13px] text-sig-text-2">
                      {conversation.members_count} members
                    </span>
                  )}
                </span>
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${
                    checked ? "border-transparent bg-ultramarine text-white" : ""
                  }`}
                  style={checked ? undefined : { borderColor: "var(--sig-border)" }}
                >
                  {checked && <CheckIcon size={13} />}
                </span>
              </button>
            );
          })
        )}
      </div>
    </Modal>
  );
}
