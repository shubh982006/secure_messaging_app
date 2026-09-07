"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { presenceLabel } from "@/lib/format";
import { useStore } from "@/lib/store";
import type { Conversation, User } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { Modal, PrimaryButton } from "@/components/Modal";
import {
  BellIcon,
  LeaveIcon,
  LockIcon,
  MuteIcon,
  PlusIcon,
  SearchIcon,
  TimerIcon,
  TrashIcon,
} from "@/components/icons";

/** Signal's retention presets. */
const DISAPPEAR_OPTIONS = [
  { seconds: 0, label: "Off" },
  { seconds: 30, label: "30 seconds" },
  { seconds: 5 * 60, label: "5 minutes" },
  { seconds: 60 * 60, label: "1 hour" },
  { seconds: 8 * 60 * 60, label: "8 hours" },
  { seconds: 24 * 60 * 60, label: "1 day" },
  { seconds: 7 * 24 * 60 * 60, label: "1 week" },
];

export function disappearLabel(seconds: number): string {
  return DISAPPEAR_OPTIONS.find((o) => o.seconds === seconds)?.label ?? `${seconds}s`;
}

/** Contact info for a DM, group info + member management for a group. */
export function InfoModal({
  open,
  onClose,
  conversation,
}: {
  open: boolean;
  onClose: () => void;
  conversation: Conversation | null;
}) {
  const router = useRouter();
  const me = useStore((state) => state.me);
  const upsertConversation = useStore((state) => state.upsertConversation);
  const toast = useStore((state) => state.toast);

  const [detail, setDetail] = useState<Conversation | null>(conversation);
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [candidates, setCandidates] = useState<User[]>([]);
  const [renaming, setRenaming] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [timerOpen, setTimerOpen] = useState(false);

  const isGroup = conversation?.type === "group";
  const isAdmin = detail?.my_role === "admin";

  const conversationId = conversation?.id ?? null;

  // Keyed on the id, not the object: the conversation gets a new identity on
  // every store update (a new message, a presence change), and resetting the
  // panels on those would slam any open picker shut mid-interaction.
  useEffect(() => {
    if (!open || !conversationId) return;
    setAdding(false);
    setRenaming(false);
    setTimerOpen(false);
    setQuery("");
    api
      .conversation(conversationId)
      .then((fresh) => {
        setDetail(fresh);
        setDraftName(fresh.name ?? "");
        upsertConversation(fresh);
      })
      .catch(() => {});
  }, [open, conversationId, upsertConversation]);

  // Keep live fields (presence, last message, membership) fresh without
  // discarding the members we fetched above or closing anything.
  useEffect(() => {
    if (!conversation) return;
    setDetail((current) =>
      current && current.id === conversation.id
        ? { ...current, ...conversation, members: current.members ?? conversation.members }
        : conversation,
    );
  }, [conversation]);

  useEffect(() => {
    if (!adding) return;
    const handle = setTimeout(() => {
      api.searchUsers(query).then((response) => setCandidates(response.results)).catch(() => {});
    }, 180);
    return () => clearTimeout(handle);
  }, [query, adding]);

  if (!conversation || !detail) return null;

  async function refresh() {
    const fresh = await api.conversation(conversation!.id);
    setDetail(fresh);
    upsertConversation(fresh);
  }

  async function addMember(user: User) {
    try {
      await api.addMembers(conversation!.id, [user.id]);
      await refresh();
      toast(`${user.display_name ?? "Member"} added`);
    } catch {
      toast("Could not add that member", "error");
    }
  }

  async function removeMember(userId: string, name: string) {
    try {
      await api.removeMember(conversation!.id, userId);
      await refresh();
      toast(`${name} removed`);
    } catch {
      toast("Could not remove that member", "error");
    }
  }

  async function rename() {
    try {
      const updated = await api.updateConversation(conversation!.id, { name: draftName.trim() });
      setDetail(updated);
      upsertConversation(updated);
      setRenaming(false);
      toast("Group renamed");
    } catch {
      toast("Could not rename the group", "error");
    }
  }

  async function setDisappearing(seconds: number) {
    try {
      const updated = await api.updateConversation(conversation!.id, {
        disappear_seconds: seconds,
      });
      setDetail((current) => (current ? { ...current, disappear_seconds: seconds } : current));
      upsertConversation(updated);
      setTimerOpen(false);
      toast(
        seconds === 0
          ? "Disappearing messages turned off"
          : `New messages disappear after ${disappearLabel(seconds)}`,
      );
    } catch {
      toast("Could not update disappearing messages", "error");
    }
  }

  async function leave() {
    try {
      await api.leaveConversation(conversation!.id);
      useStore.setState((state) => ({
        conversations: state.conversations.filter((c) => c.id !== conversation!.id),
      }));
      onClose();
      router.push("/chats");
      toast("You left the group");
    } catch {
      toast("Could not leave the group", "error");
    }
  }

  const memberIds = new Set(detail.members?.map((member) => member.user_id) ?? []);
  const addable = candidates.filter((user) => !memberIds.has(user.id));

  return (
    <Modal
      open={open}
      title={isGroup ? "Group info" : "Contact info"}
      onClose={onClose}
      width={440}
    >
      <div className="flex flex-col items-center pb-4 pt-1 text-center">
        <Avatar
          name={detail.name}
          src={detail.avatar_url}
          seed={detail.peer?.id ?? detail.id}
          size={92}
          isGroup={isGroup}
        />

        {renaming ? (
          <div className="mt-4 flex w-full max-w-[280px] gap-2">
            <input
              autoFocus
              value={draftName}
              onChange={(event) => setDraftName(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void rename()}
              className="focus-ring flex-1 rounded-lg bg-sig-input px-3 py-2 text-[15px] text-sig-text"
            />
            <PrimaryButton onClick={() => void rename()} disabled={!draftName.trim()}>
              Save
            </PrimaryButton>
          </div>
        ) : (
          <button
            disabled={!isGroup || !isAdmin}
            onClick={() => setRenaming(true)}
            className="mt-3.5 rounded-lg px-2 py-0.5 text-[20px] font-semibold text-sig-text disabled:cursor-default enabled:hover:bg-sig-hover"
            title={isGroup && isAdmin ? "Rename group" : undefined}
          >
            {detail.name}
          </button>
        )}

        <p className="mt-1 text-[13.5px] text-sig-text-2">
          {isGroup
            ? `${detail.members_count} members`
            : presenceLabel(detail.is_online, detail.last_seen_at)}
        </p>
        {!isGroup && detail.peer?.about && (
          <p className="mt-2 max-w-[300px] text-[13.5px] text-sig-text-2">
            {detail.peer.about}
          </p>
        )}
      </div>

      <div className="mb-4 flex gap-2">
        <button
          onClick={() => {
            api
              .updateConversation(detail.id, { muted: !detail.muted })
              .then((updated) => {
                setDetail({ ...detail, muted: updated.muted });
                upsertConversation(updated);
                toast(updated.muted ? "Chat muted" : "Chat unmuted");
              })
              .catch(() => toast("Could not update that chat", "error"));
          }}
          className="flex flex-1 flex-col items-center gap-1.5 rounded-lg py-3 text-[12.5px] text-sig-text-2 transition-colors hover:bg-sig-hover"
        >
          {detail.muted ? <BellIcon size={19} /> : <MuteIcon size={19} />}
          {detail.muted ? "Unmute" : "Mute"}
        </button>
        <button
          onClick={() => setTimerOpen((open) => !open)}
          className={`flex flex-1 flex-col items-center gap-1.5 rounded-lg py-3 text-[12.5px] transition-colors hover:bg-sig-hover ${
            detail.disappear_seconds > 0 ? "text-ultramarine-light" : "text-sig-text-2"
          }`}
        >
          <TimerIcon size={19} />
          {detail.disappear_seconds > 0
            ? disappearLabel(detail.disappear_seconds)
            : "Disappearing"}
        </button>
        {isGroup && (
          <button
            onClick={() => void leave()}
            className="flex flex-1 flex-col items-center gap-1.5 rounded-lg py-3 text-[12.5px] text-sig-danger transition-colors hover:bg-sig-hover"
          >
            <LeaveIcon size={19} />
            Leave
          </button>
        )}
      </div>

      {timerOpen && (
        <div
          className="animate-fade-up mb-4 rounded-xl border p-2"
          style={{ borderColor: "var(--sig-border)" }}
        >
          <p className="px-2 pb-1.5 pt-1 text-[12.5px] leading-relaxed text-sig-text-2">
            New messages in this chat will disappear after the selected time. Messages
            already sent are not affected.
          </p>
          {DISAPPEAR_OPTIONS.map((option) => (
            <button
              key={option.seconds}
              onClick={() => void setDisappearing(option.seconds)}
              className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-[14px] text-sig-text transition-colors hover:bg-sig-hover"
            >
              {option.label}
              <span
                className={`flex h-4 w-4 items-center justify-center rounded-full border-2 ${
                  detail.disappear_seconds === option.seconds
                    ? "border-ultramarine bg-ultramarine"
                    : "border-sig-border"
                }`}
              >
                {detail.disappear_seconds === option.seconds && (
                  <span className="h-1.5 w-1.5 rounded-full bg-white" />
                )}
              </span>
            </button>
          ))}
        </div>
      )}

      {isGroup && (
        <>
          <div className="mb-1 flex items-center justify-between px-1">
            <p className="text-[12px] font-medium uppercase tracking-wider text-sig-text-3">
              {detail.members_count} members
            </p>
            {isAdmin && (
              <button
                onClick={() => setAdding((value) => !value)}
                className="flex items-center gap-1 text-[13px] font-medium text-ultramarine-light hover:opacity-80"
              >
                <PlusIcon size={14} />
                Add
              </button>
            )}
          </div>

          {adding && (
            <div className="mb-3 rounded-lg border border-sig-border p-2">
              <div className="relative mb-1.5">
                <SearchIcon
                  size={15}
                  className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-sig-text-3"
                />
                <input
                  autoFocus
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search people"
                  className="focus-ring w-full rounded-full bg-sig-input py-2 pl-8 pr-3 text-[13.5px] text-sig-text placeholder:text-sig-text-3"
                />
              </div>
              {addable.length === 0 ? (
                <p className="px-2 py-3 text-center text-[13px] text-sig-text-3">
                  Everyone matching is already in this group
                </p>
              ) : (
                addable.map((user) => (
                  <button
                    key={user.id}
                    onClick={() => void addMember(user)}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-sig-hover"
                  >
                    <Avatar name={user.display_name} src={user.avatar_url} seed={user.id} size={30} />
                    <span className="truncate text-[14px] text-sig-text">
                      {user.display_name}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}

          <div className="pb-2">
            {detail.members?.map((member) => (
              <div
                key={member.user_id}
                className="group/member flex items-center gap-3 rounded-lg px-2 py-2"
              >
                <Avatar
                  name={member.display_name}
                  src={member.avatar_url}
                  seed={member.user_id}
                  size={38}
                  online={member.is_online}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] text-sig-text">
                    {member.user_id === me?.id ? "You" : member.display_name}
                  </span>
                  <span className="block truncate text-[12.5px] text-sig-text-3">
                    {member.about ?? (member.username ? `@${member.username}` : "")}
                  </span>
                </span>

                {member.role === "admin" && (
                  <span className="rounded px-1.5 py-0.5 text-[11px] font-medium text-sig-text-2" style={{ background: "var(--sig-hover)" }}>
                    Admin
                  </span>
                )}

                {isAdmin && member.user_id !== me?.id && (
                  <button
                    onClick={() =>
                      void removeMember(member.user_id, member.display_name ?? "Member")
                    }
                    aria-label={`Remove ${member.display_name}`}
                    title="Remove from group"
                    className="rounded-full p-1.5 text-sig-text-3 opacity-0 transition-opacity hover:bg-sig-hover hover:text-sig-danger group-hover/member:opacity-100"
                  >
                    <TrashIcon size={15} />
                  </button>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      <p className="flex items-center justify-center gap-1.5 border-t border-sig-border py-4 text-center text-[12px] text-sig-text-3">
        <LockIcon size={12} />
        Messages are secured. Encryption is mocked in this build.
      </p>
    </Modal>
  );
}
