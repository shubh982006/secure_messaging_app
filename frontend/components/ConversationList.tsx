"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { listTimestamp } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Conversation, MessageSearchHit } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { ConversationRow } from "@/components/ConversationRow";
import { CloseIcon, ComposeIcon, SearchIcon, SignalLogo } from "@/components/icons";

/**
 * Signal's left pane: your avatar + compose button, a search field, then the
 * conversation list sorted by most recent activity.
 */
export function ConversationList({
  activeId,
  onNewChat,
  onOpenProfile,
}: {
  activeId: string | null;
  onNewChat: () => void;
  onOpenProfile: () => void;
}) {
  const router = useRouter();
  const me = useStore((state) => state.me);
  const conversations = useStore((state) => state.conversations);
  const typing = useStore((state) => state.typing);
  const status = useStore((state) => state.status);
  const search = useStore((state) => state.search);
  const setSearch = useStore((state) => state.setSearch);

  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [hits, setHits] = useState<MessageSearchHit[]>([]);
  const [searching, setSearching] = useState(false);

  // Full-text search across every conversation, debounced so a fast typist
  // does not fire a query per keystroke.
  useEffect(() => {
    const term = search.trim();
    if (term.length < 2) {
      setHits([]);
      setSearching(false);
      return;
    }
    setSearching(true);
    let cancelled = false;
    const handle = setTimeout(() => {
      api
        .searchMessages(term)
        .then((response) => {
          if (!cancelled) setHits(response.results);
        })
        .catch(() => {
          if (!cancelled) setHits([]);
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [search]);

  const visible = useMemo(() => {
    const term = search.trim().toLowerCase();
    return conversations.filter((conversation) => {
      if (filter === "unread" && conversation.unread_count === 0) return false;
      if (!term) return true;
      return (
        (conversation.name ?? "").toLowerCase().includes(term) ||
        (conversation.last_message?.preview ?? "").toLowerCase().includes(term) ||
        (conversation.peer?.username ?? "").toLowerCase().includes(term)
      );
    });
  }, [conversations, search, filter]);

  const unreadTotal = conversations.reduce((total, c) => total + c.unread_count, 0);

  return (
    <aside
      className="flex h-full w-full shrink-0 flex-col border-r md:w-[320px] lg:w-[360px] xl:w-[400px]"
      style={{ background: "var(--sig-pane)", borderColor: "var(--sig-border)" }}
    >
      <header className="px-4 pb-2 pt-4">
        <div className="mb-3 flex items-center justify-between">
          <button
            onClick={onOpenProfile}
            className="focus-ring flex items-center gap-2.5 rounded-full pr-2 md:hidden"
            aria-label="Your profile"
          >
            <Avatar name={me?.display_name} src={me?.avatar_url} seed={me?.id} size={32} />
          </button>

          <h1 className="hidden items-center gap-2 text-[20px] font-semibold text-sig-text md:flex">
            Chats
            {status !== "open" && (
              <span
                className="rounded-full px-2 py-0.5 text-[11px] font-medium"
                style={{ background: "var(--sig-hover)", color: "var(--sig-text-2)" }}
                title="The socket is down; messages fall back to REST and resync on reconnect."
              >
                {status === "reconnecting" ? "Reconnecting…" : "Offline"}
              </span>
            )}
          </h1>

          <button
            onClick={onNewChat}
            aria-label="New chat"
            title="New chat"
            className="focus-ring flex h-9 w-9 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text"
          >
            <ComposeIcon size={19} />
          </button>
        </div>

        <div className="relative">
          <SearchIcon
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sig-text-3"
          />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search"
            aria-label="Search chats"
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setSearch("");
                event.currentTarget.blur();
              }
            }}
            className="focus-ring w-full rounded-full border border-transparent bg-sig-input py-2 pl-9 pr-9 text-[14px] text-sig-text placeholder:text-sig-text-3 focus:border-sig-border"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-sig-text-3 hover:text-sig-text"
            >
              <CloseIcon size={14} />
            </button>
          )}
        </div>

        <div className="mt-3 flex gap-2">
          {(["all", "unread"] as const).map((key) => (
            <button
              key={key}
              onClick={() => setFilter(key)}
              className={`focus-ring rounded-full px-3 py-1 text-[13px] font-medium capitalize transition-colors ${
                filter === key
                  ? "bg-sig-active text-sig-text"
                  : "text-sig-text-2 hover:bg-sig-hover"
              }`}
            >
              {key}
              {key === "unread" && unreadTotal > 0 && ` · ${unreadTotal}`}
            </button>
          ))}
        </div>
      </header>

      <div className="sig-scroll flex-1 overflow-y-auto pb-4 pt-1">
        {visible.length === 0 && hits.length === 0 ? (
          <EmptyList
            search={search}
            filter={filter}
            searching={searching}
            onNewChat={onNewChat}
          />
        ) : (
          <>
            {visible.length > 0 && (
              <>
                {search.trim().length >= 2 && (
                  <SectionLabel>Chats</SectionLabel>
                )}
                {visible.map((conversation: Conversation) => (
                  <ConversationRow
                    key={conversation.id}
                    conversation={conversation}
                    active={conversation.id === activeId}
                    meId={me?.id ?? ""}
                    typingNames={(typing[conversation.id] ?? []).map((entry) => entry.name)}
                    onSelect={() => router.push(`/chats/${conversation.id}`)}
                  />
                ))}
              </>
            )}

            {hits.length > 0 && (
              <>
                <SectionLabel>
                  Messages{searching ? "" : ` · ${hits.length}`}
                </SectionLabel>
                {hits.map((hit) => (
                  <SearchHitRow
                    key={hit.message.id}
                    hit={hit}
                    term={search.trim()}
                    onSelect={() => {
                      router.push(`/chats/${hit.conversation_id}`);
                      // Give the thread a moment to mount before scrolling.
                      setTimeout(() => {
                        document
                          .getElementById(`message-${hit.message.id}`)
                          ?.scrollIntoView({ behavior: "smooth", block: "center" });
                      }, 400);
                    }}
                  />
                ))}
              </>
            )}
          </>
        )}
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-4 pb-1 pt-3 text-[11.5px] font-medium uppercase tracking-wider text-sig-text-3">
      {children}
    </p>
  );
}

/** One full-text search result: which chat it came from, plus the excerpt. */
function SearchHitRow({
  hit,
  term,
  onSelect,
}: {
  hit: MessageSearchHit;
  term: string;
  onSelect: () => void;
}) {
  const pieces = hit.snippet.split(new RegExp(`(${escapeRegExp(term)})`, "ig"));
  return (
    <button
      onClick={onSelect}
      className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition-colors hover:bg-sig-hover"
    >
      <Avatar
        name={hit.conversation_name}
        seed={hit.conversation_id}
        size={40}
        isGroup={hit.conversation_type === "group"}
      />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-2">
          <span className="truncate text-[14.5px] font-medium text-sig-text">
            {hit.conversation_name ?? "Unknown"}
          </span>
          <span className="shrink-0 text-[11.5px] text-sig-text-3">
            {listTimestamp(hit.message.created_at)}
          </span>
        </span>
        <span className="mt-0.5 line-clamp-2 block text-[13.5px] text-sig-text-2">
          {pieces.map((piece, index) =>
            piece.toLowerCase() === term.toLowerCase() ? (
              <mark
                key={index}
                className="rounded bg-transparent font-semibold text-ultramarine-light"
              >
                {piece}
              </mark>
            ) : (
              <span key={index}>{piece}</span>
            ),
          )}
        </span>
      </span>
    </button>
  );
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function EmptyList({
  search,
  filter,
  searching,
  onNewChat,
}: {
  search: string;
  filter: "all" | "unread";
  searching: boolean;
  onNewChat: () => void;
}) {
  return (
    <div className="flex flex-col items-center px-8 py-14 text-center">
      <SignalLogo size={34} className="mb-3 text-sig-text-3" />
      <p className="text-[14px] text-sig-text-2">
        {searching
          ? "Searching…"
          : search
            ? `Nothing matching “${search}”`
            : filter === "unread"
              ? "You're all caught up"
              : "No chats yet"}
      </p>
      {!search && filter === "all" && (
        <button
          onClick={onNewChat}
          className="mt-3 text-[14px] font-medium text-ultramarine-light hover:opacity-80"
        >
          Start a new chat
        </button>
      )}
    </div>
  );
}
