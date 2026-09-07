"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { User } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { Modal, PrimaryButton } from "@/components/Modal";
import { GroupIcon, SearchIcon } from "@/components/icons";

/** Signal's "New chat" sheet: search people, or start a new group. */
export function NewChatModal({
  open,
  onClose,
  onNewGroup,
}: {
  open: boolean;
  onClose: () => void;
  onNewGroup: () => void;
}) {
  const router = useRouter();
  const upsertConversation = useStore((state) => state.upsertConversation);
  const toast = useStore((state) => state.toast);

  const [query, setQuery] = useState("");
  const [results, setResults] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    let cancelled = false;
    api
      .searchUsers("")
      .then((response) => !cancelled && setResults(response.results))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    // Debounce so a fast typist does not fire a request per keystroke.
    const handle = setTimeout(() => {
      api
        .searchUsers(query)
        .then((response) => setResults(response.results))
        .catch(() => {});
    }, 180);
    return () => clearTimeout(handle);
  }, [query, open]);

  async function startChat(user: User) {
    setBusy(true);
    try {
      const conversation = await api.startDirect(user.id);
      upsertConversation(conversation);
      onClose();
      router.push(`/chats/${conversation.id}`);
    } catch {
      toast("Could not start that chat", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} title="New chat" onClose={onClose}>
      <div className="relative mb-3">
        <SearchIcon
          size={16}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sig-text-3"
        />
        <input
          autoFocus
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Name, username or number"
          className="focus-ring w-full rounded-full bg-sig-input py-2.5 pl-9 pr-3 text-[14px] text-sig-text placeholder:text-sig-text-3"
        />
      </div>

      <button
        onClick={() => {
          onClose();
          onNewGroup();
        }}
        className="mb-2 flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-sig-hover"
      >
        <span className="flex h-11 w-11 items-center justify-center rounded-full bg-ultramarine text-white">
          <GroupIcon size={20} />
        </span>
        <span className="text-[15px] font-medium text-sig-text">New group</span>
      </button>

      <p className="px-2 pb-1 pt-2 text-[12px] font-medium uppercase tracking-wider text-sig-text-3">
        {query.trim() ? "Results" : "Contacts"}
      </p>

      <div className="pb-2">
        {results.length === 0 ? (
          <p className="px-2 py-6 text-center text-[13.5px] text-sig-text-3">
            {query.trim() ? "Nobody matches that search" : "No contacts yet"}
          </p>
        ) : (
          results.map((user) => (
            <button
              key={user.id}
              disabled={busy}
              onClick={() => void startChat(user)}
              className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-sig-hover disabled:opacity-50"
            >
              <Avatar
                name={user.display_name}
                src={user.avatar_url}
                seed={user.id}
                size={40}
                online={user.is_online}
              />
              <span className="min-w-0">
                <span className="block truncate text-[15px] text-sig-text">
                  {user.display_name ?? "Unknown"}
                </span>
                <span className="block truncate text-[13px] text-sig-text-2">
                  {user.about ?? (user.username ? `@${user.username}` : "")}
                </span>
              </span>
            </button>
          ))
        )}
      </div>
    </Modal>
  );
}

/** Multi-select sheet used for both "New group" and "Add members". */
export function NewGroupModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const upsertConversation = useStore((state) => state.upsertConversation);
  const toast = useStore((state) => state.toast);

  const [name, setName] = useState("");
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<User[]>([]);
  const [selected, setSelected] = useState<User[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    setName("");
    setQuery("");
    setSelected([]);
    api.searchUsers("").then((response) => setCandidates(response.results)).catch(() => {});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handle = setTimeout(() => {
      api.searchUsers(query).then((response) => setCandidates(response.results)).catch(() => {});
    }, 180);
    return () => clearTimeout(handle);
  }, [query, open]);

  function toggle(user: User) {
    setSelected((current) =>
      current.some((item) => item.id === user.id)
        ? current.filter((item) => item.id !== user.id)
        : [...current, user],
    );
  }

  async function create() {
    setBusy(true);
    try {
      const conversation = await api.createGroup(
        name.trim(),
        selected.map((user) => user.id),
      );
      upsertConversation(conversation);
      onClose();
      router.push(`/chats/${conversation.id}`);
      toast("Group created");
    } catch {
      toast("Could not create that group", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="New group"
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <PrimaryButton tone="ghost" onClick={onClose}>
            Cancel
          </PrimaryButton>
          <PrimaryButton
            disabled={busy || !name.trim() || selected.length === 0}
            onClick={() => void create()}
          >
            {busy ? "Creating…" : `Create${selected.length ? ` (${selected.length})` : ""}`}
          </PrimaryButton>
        </div>
      }
    >
      <input
        autoFocus
        value={name}
        onChange={(event) => setName(event.target.value)}
        placeholder="Group name"
        maxLength={80}
        className="focus-ring mb-3 w-full rounded-lg border border-sig-border bg-sig-input px-3.5 py-2.5 text-[15px] text-sig-text placeholder:text-sig-text-3"
      />

      {selected.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {selected.map((user) => (
            <button
              key={user.id}
              onClick={() => toggle(user)}
              className="flex items-center gap-1.5 rounded-full bg-sig-hover py-1 pl-1 pr-2.5 text-[13px] text-sig-text transition-colors hover:bg-sig-active"
            >
              <Avatar name={user.display_name} src={user.avatar_url} seed={user.id} size={20} />
              {user.display_name?.split(" ")[0]}
              <span className="text-sig-text-3">×</span>
            </button>
          ))}
        </div>
      )}

      <div className="relative mb-2">
        <SearchIcon
          size={16}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sig-text-3"
        />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Add members"
          className="focus-ring w-full rounded-full bg-sig-input py-2.5 pl-9 pr-3 text-[14px] text-sig-text placeholder:text-sig-text-3"
        />
      </div>

      <div className="pb-2">
        {candidates.map((user) => {
          const checked = selected.some((item) => item.id === user.id);
          return (
            <button
              key={user.id}
              onClick={() => toggle(user)}
              className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-sig-hover"
            >
              <Avatar name={user.display_name} src={user.avatar_url} seed={user.id} size={38} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[15px] text-sig-text">
                  {user.display_name ?? "Unknown"}
                </span>
              </span>
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-full border-2 ${
                  checked ? "border-ultramarine bg-ultramarine" : "border-sig-border"
                }`}
              >
                {checked && (
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round">
                    <path d="m4 12 5 5L20 6" />
                  </svg>
                )}
              </span>
            </button>
          );
        })}
      </div>
    </Modal>
  );
}
