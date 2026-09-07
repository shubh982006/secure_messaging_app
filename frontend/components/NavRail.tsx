"use client";

import { useState } from "react";

import { useStore } from "@/lib/store";
import { Avatar } from "@/components/Avatar";
import {
  CallIcon,
  ChatsIcon,
  SettingsIcon,
  StoriesIcon,
} from "@/components/icons";

/**
 * Signal Desktop's narrow left rail: Chats / Calls / Stories at the top, the
 * user's avatar and settings at the bottom. Calls and Stories are placeholders
 * per the brief, so they announce themselves rather than dead-ending.
 */
export function NavRail({
  onOpenSettings,
  onOpenProfile,
}: {
  onOpenSettings: () => void;
  onOpenProfile: () => void;
}) {
  const me = useStore((state) => state.me);
  const toast = useStore((state) => state.toast);
  const unread = useStore((state) =>
    state.conversations.reduce((total, c) => total + c.unread_count, 0),
  );
  const [tab, setTab] = useState<"chats" | "calls" | "stories">("chats");

  const items = [
    { key: "chats" as const, label: "Chats", Icon: ChatsIcon, badge: unread },
    { key: "calls" as const, label: "Calls", Icon: CallIcon, badge: 0 },
    { key: "stories" as const, label: "Stories", Icon: StoriesIcon, badge: 0 },
  ];

  return (
    <nav
      className="hidden w-[68px] shrink-0 flex-col items-center justify-between border-r py-4 md:flex"
      style={{ background: "var(--sig-rail)", borderColor: "var(--sig-border)" }}
      aria-label="Primary"
    >
      <div className="flex flex-col items-center gap-1.5">
        {items.map(({ key, label, Icon, badge }) => (
          <button
            key={key}
            title={label}
            aria-label={label}
            aria-current={tab === key}
            onClick={() => {
              if (key === "chats") {
                setTab(key);
                return;
              }
              toast(`${label} are coming soon`);
            }}
            className={`focus-ring relative flex h-11 w-11 items-center justify-center rounded-full transition-colors ${
              tab === key
                ? "bg-sig-active text-sig-text"
                : "text-sig-text-2 hover:bg-sig-hover hover:text-sig-text"
            }`}
          >
            <Icon size={22} />
            {badge > 0 && (
              <span className="absolute right-1 top-1 flex h-[17px] min-w-[17px] items-center justify-center rounded-full bg-ultramarine px-1 text-[10px] font-semibold leading-none text-white">
                {badge > 99 ? "99+" : badge}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="flex flex-col items-center gap-2">
        <button
          onClick={onOpenSettings}
          title="Settings"
          aria-label="Settings"
          className="focus-ring flex h-11 w-11 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text"
        >
          <SettingsIcon size={21} />
        </button>
        <button
          onClick={onOpenProfile}
          title={me?.display_name ?? "Profile"}
          aria-label="Your profile"
          className="focus-ring rounded-full transition-transform hover:scale-105"
        >
          <Avatar
            name={me?.display_name}
            src={me?.avatar_url}
            seed={me?.id}
            size={32}
          />
        </button>
      </div>
    </nav>
  );
}
