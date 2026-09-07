"use client";

import { memo } from "react";

import { listTimestamp } from "@/lib/format";
import type { Conversation } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { MuteIcon, StatusTick } from "@/components/icons";

interface Props {
  conversation: Conversation;
  active: boolean;
  meId: string;
  typingNames: string[];
  onSelect: () => void;
}

function ConversationRowBase({
  conversation,
  active,
  meId,
  typingNames,
  onSelect,
}: Props) {
  const last = conversation.last_message;
  const isGroup = conversation.type === "group";
  const outgoing = last?.sender_id === meId;
  const unread = conversation.unread_count > 0;

  let preview: React.ReactNode;
  if (typingNames.length > 0) {
    preview = (
      <span className="text-ultramarine-light">
        {isGroup && typingNames.length === 1
          ? `${typingNames[0].split(" ")[0]} is typing…`
          : "typing…"}
      </span>
    );
  } else if (!last) {
    preview = <span className="italic text-sig-text-3">No messages yet</span>;
  } else if (last.type === "system") {
    preview = <span className="italic">{last.preview}</span>;
  } else {
    preview = (
      <>
        {isGroup && !outgoing && last.sender_name && (
          <span className="text-sig-text-2">{last.sender_name.split(" ")[0]}: </span>
        )}
        {last.deleted ? (
          <span className="italic">This message was deleted</span>
        ) : (
          last.preview
        )}
      </>
    );
  }

  return (
    <button
      onClick={onSelect}
      aria-current={active}
      className={`flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors ${
        active ? "bg-sig-active" : "hover:bg-sig-hover"
      }`}
    >
      <Avatar
        name={conversation.name}
        src={conversation.avatar_url}
        seed={conversation.peer?.id ?? conversation.id}
        size={48}
        isGroup={isGroup}
        online={!isGroup && conversation.is_online}
      />

      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span
            className={`truncate text-[15px] ${
              unread ? "font-semibold text-sig-text" : "font-medium text-sig-text"
            }`}
          >
            {conversation.name ?? "Unknown"}
          </span>
          <span
            className={`shrink-0 text-[12px] ${
              unread ? "font-medium text-ultramarine-light" : "text-sig-text-3"
            }`}
          >
            {last ? listTimestamp(last.created_at) : ""}
          </span>
        </span>

        <span className="mt-0.5 flex items-center gap-1.5">
          {/* Outgoing ticks appear in the list exactly as they do in Signal. */}
          {outgoing &&
            last &&
            last.type !== "system" &&
            !last.deleted &&
            typingNames.length === 0 && (
            <StatusTick
              status={last.status}
              className={
                last.status === "read" ? "text-ultramarine-light" : "text-sig-text-3"
              }
            />
          )}
          <span
            className={`min-w-0 flex-1 truncate text-[14px] ${
              unread ? "text-sig-text" : "text-sig-text-2"
            }`}
          >
            {preview}
          </span>

          {conversation.muted && <MuteIcon size={14} className="shrink-0 text-sig-text-3" />}

          {unread && (
            <span className="flex h-[19px] min-w-[19px] shrink-0 items-center justify-center rounded-full bg-ultramarine px-1.5 text-[11px] font-semibold leading-none text-white">
              {conversation.unread_count > 99 ? "99+" : conversation.unread_count}
            </span>
          )}
        </span>
      </span>
    </button>
  );
}

export const ConversationRow = memo(ConversationRowBase);
