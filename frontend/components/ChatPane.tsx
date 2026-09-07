"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { dayDivider, presenceLabel, sameDay } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Attachment, Conversation, Member, Message } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { Lightbox } from "@/components/Attachments";
import { Composer } from "@/components/Composer";
import { MessageBubble } from "@/components/MessageBubble";
import {
  BackIcon,
  BellIcon,
  CallIcon,
  KebabIcon,
  LeaveIcon,
  MuteIcon,
  SearchIcon,
  TimerIcon,
  UserIcon,
  VideoIcon,
} from "@/components/icons";

interface Props {
  conversation: Conversation;
  onOpenInfo: () => void;
}

export function ChatPane({ conversation, onOpenInfo }: Props) {
  const router = useRouter();
  const me = useStore((state) => state.me);
  const messages = useStore((state) => state.messages[conversation.id]);
  const loading = useStore((state) => state.loadingThread[conversation.id]);
  const hasMore = useStore((state) => state.hasMore[conversation.id]);
  const typing = useStore((state) => state.typing[conversation.id]);
  const loadOlder = useStore((state) => state.loadOlder);
  const markRead = useStore((state) => state.markRead);
  const deleteMessage = useStore((state) => state.deleteMessage);
  const toggleReaction = useStore((state) => state.toggleReaction);
  const upsertConversation = useStore((state) => state.upsertConversation);
  const toast = useStore((state) => state.toast);

  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [threadSearch, setThreadSearch] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<Attachment | null>(null);
  const [droppedFiles, setDroppedFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);

  const scroller = useRef<HTMLDivElement>(null);
  const bottomAnchor = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const previousLastId = useRef<string | null>(null);

  const isGroup = conversation.type === "group";
  const thread = useMemo(() => messages ?? [], [messages]);

  const membersById = useMemo(() => {
    const map = new Map<string, Member>();
    conversation.members?.forEach((member) => map.set(member.user_id, member));
    return map;
  }, [conversation.members]);

  // Group chats need member names for bubbles; the list payload omits them.
  useEffect(() => {
    if (isGroup && !conversation.members) {
      api.conversation(conversation.id).then(upsertConversation).catch(() => {});
    }
  }, [isGroup, conversation.id, conversation.members, upsertConversation]);

  // Mark read whenever the thread is open, focused, and something new arrives.
  useEffect(() => {
    const last = thread[thread.length - 1];
    if (!last) return;
    if (previousLastId.current === last.id) return;
    previousLastId.current = last.id;
    if (document.visibilityState === "visible") markRead(conversation.id);
  }, [thread, conversation.id, markRead]);

  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState === "visible") markRead(conversation.id);
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => document.removeEventListener("visibilitychange", onVisible);
  }, [conversation.id, markRead]);

  // Autoscroll, but never yank the view while someone reads back through history.
  useEffect(() => {
    if (stickToBottom.current) {
      bottomAnchor.current?.scrollIntoView({ block: "end" });
    }
  }, [thread.length, typing?.length]);

  useEffect(() => {
    stickToBottom.current = true;
    previousLastId.current = null;
    setReplyTo(null);
    setThreadSearch(null);
    setLightbox(null);
    setDragging(false);
  }, [conversation.id]);

  // Ctrl/Cmd+F focuses in-thread search; the shell owns the global shortcuts.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const meta = event.metaKey || event.ctrlKey;
      if (meta && event.key.toLowerCase() === "f") {
        event.preventDefault();
        setThreadSearch((value) => (value === null ? "" : value));
      }
      if (event.key === "Escape") {
        if (lightbox) return; // the lightbox closes itself
        if (threadSearch !== null) setThreadSearch(null);
        else if (replyTo) setReplyTo(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [lightbox, threadSearch, replyTo]);

  const onScroll = useCallback(() => {
    const element = scroller.current;
    if (!element) return;
    const distanceFromBottom =
      element.scrollHeight - element.scrollTop - element.clientHeight;
    stickToBottom.current = distanceFromBottom < 120;

    if (element.scrollTop < 160 && hasMore) {
      const previousHeight = element.scrollHeight;
      void loadOlder(conversation.id).then(() => {
        requestAnimationFrame(() => {
          // Keep the reader's place when older messages are prepended.
          element.scrollTop = element.scrollHeight - previousHeight;
        });
      });
    }
  }, [conversation.id, hasMore, loadOlder]);

  const visibleThread = useMemo(() => {
    if (!threadSearch?.trim()) return thread;
    const term = threadSearch.toLowerCase();
    return thread.filter((message) =>
      (message.content ?? "").toLowerCase().includes(term),
    );
  }, [thread, threadSearch]);

  const subtitle = isGroup
    ? `${conversation.members_count} members`
    : presenceLabel(conversation.is_online, conversation.last_seen_at);

  const typingNames = (typing ?? []).map((entry) => entry.name);

  return (
    <section
      className="sig-canvas relative flex h-full min-w-0 flex-1 flex-col"
      onDragOver={(event) => {
        if (event.dataTransfer.types.includes("Files")) {
          event.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(event) => {
        if (event.currentTarget === event.target) setDragging(false);
      }}
      onDrop={(event) => {
        if (!event.dataTransfer.files.length) return;
        event.preventDefault();
        setDragging(false);
        setDroppedFiles(Array.from(event.dataTransfer.files));
      }}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-30 flex items-center justify-center bg-sig-bg/85">
          <div className="rounded-2xl border-2 border-dashed border-ultramarine px-10 py-8 text-center">
            <p className="text-[15px] font-medium text-sig-text">Drop to attach</p>
            <p className="mt-1 text-[13px] text-sig-text-2">Images and files up to 10MB</p>
          </div>
        </div>
      )}
      {/* ------------------------------------------------------------ header */}
      <header
        className="flex h-[60px] shrink-0 items-center gap-3 border-b px-3 md:px-4"
        style={{ borderColor: "var(--sig-border)", background: "var(--sig-bg)" }}
      >
        <button
          onClick={() => router.push("/chats")}
          aria-label="Back to chats"
          className="focus-ring -ml-1 rounded-full p-1.5 text-sig-text-2 hover:bg-sig-hover md:hidden"
        >
          <BackIcon size={20} />
        </button>

        <button
          onClick={onOpenInfo}
          className="focus-ring flex min-w-0 flex-1 items-center gap-3 rounded-lg py-1 text-left"
        >
          <Avatar
            name={conversation.name}
            src={conversation.avatar_url}
            seed={conversation.peer?.id ?? conversation.id}
            size={36}
            isGroup={isGroup}
            online={!isGroup && conversation.is_online}
          />
          <span className="min-w-0">
            <span className="flex items-center gap-1.5">
              <span className="truncate text-[15px] font-semibold text-sig-text">
                {conversation.name ?? "Unknown"}
              </span>
              {conversation.disappear_seconds > 0 && (
                <TimerIcon
                  size={14}
                  className="shrink-0 text-ultramarine-light"
                />
              )}
            </span>
            <span className="block truncate text-[12.5px] text-sig-text-2">
              {typingNames.length > 0 ? (
                <span className="text-ultramarine-light">
                  {isGroup && typingNames.length === 1
                    ? `${typingNames[0].split(" ")[0]} is typing…`
                    : "typing…"}
                </span>
              ) : (
                subtitle
              )}
            </span>
          </span>
        </button>

        <div className="flex items-center gap-0.5">
          <HeaderButton label="Video call" onClick={() => toast("Video calls are coming soon")}>
            <VideoIcon size={20} />
          </HeaderButton>
          <HeaderButton label="Voice call" onClick={() => toast("Voice calls are coming soon")}>
            <CallIcon size={19} />
          </HeaderButton>
          <HeaderButton
            label="Search in chat"
            onClick={() => setThreadSearch((value) => (value === null ? "" : null))}
          >
            <SearchIcon size={19} />
          </HeaderButton>

          <div className="relative">
            <HeaderButton label="More options" onClick={() => setMenuOpen((open) => !open)}>
              <KebabIcon size={19} />
            </HeaderButton>

            {menuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
                <div
                  className="animate-pop absolute right-0 top-10 z-20 w-52 overflow-hidden rounded-lg border py-1"
                  style={{
                    background: "var(--sig-elevated)",
                    borderColor: "var(--sig-border)",
                    boxShadow: "var(--sig-shadow)",
                  }}
                >
                  <HeaderMenuItem
                    icon={<UserIcon size={15} />}
                    label={isGroup ? "Group info" : "Contact info"}
                    onClick={() => {
                      onOpenInfo();
                      setMenuOpen(false);
                    }}
                  />
                  <HeaderMenuItem
                    icon={conversation.muted ? <BellIcon size={15} /> : <MuteIcon size={15} />}
                    label={conversation.muted ? "Unmute" : "Mute notifications"}
                    onClick={() => {
                      api
                        .updateConversation(conversation.id, { muted: !conversation.muted })
                        .then((updated) => {
                          upsertConversation(updated);
                          toast(updated.muted ? "Chat muted" : "Chat unmuted");
                        })
                        .catch(() => toast("Could not update that chat", "error"));
                      setMenuOpen(false);
                    }}
                  />
                  {isGroup && (
                    <HeaderMenuItem
                      icon={<LeaveIcon size={15} />}
                      label="Leave group"
                      danger
                      onClick={() => {
                        api
                          .leaveConversation(conversation.id)
                          .then(() => {
                            useStore.setState((state) => ({
                              conversations: state.conversations.filter(
                                (c) => c.id !== conversation.id,
                              ),
                            }));
                            toast("You left the group");
                            router.push("/chats");
                          })
                          .catch(() => toast("Could not leave the group", "error"));
                        setMenuOpen(false);
                      }}
                    />
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {threadSearch !== null && (
        <div
          className="border-b px-4 py-2"
          style={{ borderColor: "var(--sig-border)", background: "var(--sig-bg)" }}
        >
          <input
            autoFocus
            value={threadSearch}
            onChange={(event) => setThreadSearch(event.target.value)}
            placeholder="Search in this conversation"
            className="focus-ring w-full rounded-full bg-sig-input px-4 py-1.5 text-[14px] text-sig-text placeholder:text-sig-text-3"
          />
        </div>
      )}

      {/* ---------------------------------------------------------- messages */}
      <div
        ref={scroller}
        onScroll={onScroll}
        className="sig-scroll flex-1 overflow-y-auto py-4"
      >
        {loading && (
          <p className="py-8 text-center text-[13px] text-sig-text-3">Loading messages…</p>
        )}

        {!loading && thread.length === 0 && <EmptyThread conversation={conversation} />}

        {hasMore && thread.length > 0 && (
          <p className="pb-3 text-center text-[12px] text-sig-text-3">
            Scroll up for older messages
          </p>
        )}

        {threadSearch?.trim() && visibleThread.length === 0 && (
          <p className="py-8 text-center text-[13px] text-sig-text-3">
            No messages matching “{threadSearch}”
          </p>
        )}

        {visibleThread.map((message, index) => {
          const previous = visibleThread[index - 1];
          const next = visibleThread[index + 1];
          const outgoing = message.sender_id === me?.id;
          const member = message.sender_id ? membersById.get(message.sender_id) : undefined;

          const showDivider =
            !previous || !sameDay(previous.created_at, message.created_at);

          const startsGroup =
            !previous ||
            previous.sender_id !== message.sender_id ||
            previous.type === "system" ||
            showDivider;
          const endsGroup =
            !next || next.sender_id !== message.sender_id || next.type === "system";

          return (
            <div key={message.id} id={`message-${message.id}`}>
              {showDivider && (
                <div className="my-4 flex justify-center">
                  <span className="rounded-full px-3 py-1 text-[11.5px] font-medium uppercase tracking-wide text-sig-text-3">
                    {dayDivider(message.created_at)}
                  </span>
                </div>
              )}
              <MessageBubble
                message={message}
                outgoing={outgoing}
                isGroup={isGroup}
                senderName={
                  member?.display_name ??
                  (outgoing ? me?.display_name ?? null : conversation.peer?.display_name ?? null)
                }
                senderAvatar={member?.avatar_url ?? conversation.peer?.avatar_url ?? null}
                startsGroup={startsGroup}
                endsGroup={endsGroup}
                meId={me?.id ?? ""}
                onReply={setReplyTo}
                onDelete={(target) => void deleteMessage(target.id, conversation.id)}
                onReact={(target, emoji) =>
                  void toggleReaction(target.id, conversation.id, emoji)
                }
                onCopy={(text) => {
                  void navigator.clipboard?.writeText(text);
                  toast("Copied to clipboard");
                }}
                onOpenImage={setLightbox}
              />
            </div>
          );
        })}

        {typingNames.length > 0 && <TypingBubble names={typingNames} isGroup={isGroup} />}

        <div ref={bottomAnchor} />
      </div>

      <Lightbox attachment={lightbox} onClose={() => setLightbox(null)} />

      <Composer
        conversationId={conversation.id}
        disappearSeconds={conversation.disappear_seconds}
        droppedFiles={droppedFiles}
        onDroppedFilesHandled={() => setDroppedFiles([])}
        replyTo={replyTo}
        replyToName={
          replyTo?.sender_id === me?.id
            ? "yourself"
            : (membersById.get(replyTo?.sender_id ?? "")?.display_name ??
              conversation.peer?.display_name ??
              null)
        }
        onCancelReply={() => setReplyTo(null)}
      />
    </section>
  );
}

function HeaderButton({
  label,
  onClick,
  children,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="focus-ring flex h-9 w-9 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text"
    >
      {children}
    </button>
  );
}

function HeaderMenuItem({
  icon,
  label,
  onClick,
  danger = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[14px] transition-colors hover:bg-sig-hover ${
        danger ? "text-sig-danger" : "text-sig-text"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

function TypingBubble({ names, isGroup }: { names: string[]; isGroup: boolean }) {
  return (
    <div className="mb-2 flex items-end gap-2 px-4">
      {isGroup && <div className="w-7 shrink-0" />}
      <div
        className="flex items-center gap-1 rounded-[18px] rounded-bl-[5px] px-3.5 py-3"
        style={{ background: "var(--sig-bubble-in)" }}
        aria-label={`${names.join(", ")} typing`}
      >
        {[0, 1, 2].map((index) => (
          <span
            key={index}
            className="typing-dot h-1.5 w-1.5 rounded-full bg-sig-text-2"
            style={{ animationDelay: `${index * 0.16}s` }}
          />
        ))}
      </div>
      {isGroup && names.length > 0 && (
        <span className="pb-1 text-[12px] text-sig-text-3">
          {names.length === 1 ? names[0].split(" ")[0] : `${names.length} people`}
        </span>
      )}
    </div>
  );
}

function EmptyThread({ conversation }: { conversation: Conversation }) {
  return (
    <div className="flex flex-col items-center px-8 py-16 text-center">
      <Avatar
        name={conversation.name}
        src={conversation.avatar_url}
        seed={conversation.peer?.id ?? conversation.id}
        size={72}
        isGroup={conversation.type === "group"}
      />
      <h3 className="mt-4 text-[17px] font-semibold text-sig-text">
        {conversation.name}
      </h3>
      <p className="mt-1 max-w-[320px] text-[13.5px] leading-relaxed text-sig-text-2">
        {conversation.type === "group"
          ? "This is the beginning of your group conversation."
          : "Say hello. Messages are private between you two."}
      </p>
    </div>
  );
}
