"use client";

import { useRouter } from "next/navigation";

import { formatPhone } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Avatar } from "@/components/Avatar";
import { Modal } from "@/components/Modal";
import {
  BellIcon,
  DevicesIcon,
  KeyboardIcon,
  LeaveIcon,
  LockIcon,
  PaletteIcon,
  StoriesIcon,
  UserIcon,
} from "@/components/icons";

/**
 * Settings. Appearance and sign-out are real; the rest are the placeholders
 * the brief asks for, so the surface reads complete without pretending to work.
 */
export function SettingsModal({
  open,
  onClose,
  onOpenProfile,
  onOpenShortcuts,
}: {
  open: boolean;
  onClose: () => void;
  onOpenProfile: () => void;
  onOpenShortcuts: () => void;
}) {
  const router = useRouter();
  const me = useStore((state) => state.me);
  const theme = useStore((state) => state.theme);
  const toggleTheme = useStore((state) => state.toggleTheme);
  const signOut = useStore((state) => state.signOut);
  const toast = useStore((state) => state.toast);

  const placeholders = [
    { icon: <BellIcon size={18} />, label: "Notifications" },
    { icon: <LockIcon size={18} />, label: "Privacy" },
    { icon: <DevicesIcon size={18} />, label: "Linked devices" },
    { icon: <StoriesIcon size={18} />, label: "Stories" },
  ];

  return (
    <Modal open={open} title="Settings" onClose={onClose}>
      <button
        onClick={() => {
          onClose();
          onOpenProfile();
        }}
        className="mb-4 flex w-full items-center gap-3 rounded-xl p-3 text-left transition-colors hover:bg-sig-hover"
      >
        <Avatar name={me?.display_name} src={me?.avatar_url} seed={me?.id} size={56} />
        <span className="min-w-0">
          <span className="block truncate text-[17px] font-semibold text-sig-text">
            {me?.display_name ?? "You"}
          </span>
          <span className="block text-[13px] text-sig-text-2">
            {me ? formatPhone(me.phone_number) : ""}
          </span>
          <span className="mt-0.5 block text-[12.5px] text-ultramarine-light">
            Edit profile
          </span>
        </span>
      </button>

      <Row
        icon={<PaletteIcon size={18} />}
        label="Appearance"
        value={theme === "dark" ? "Dark" : "Light"}
        onClick={toggleTheme}
      />
      <Row
        icon={<KeyboardIcon size={18} />}
        label="Keyboard shortcuts"
        value="?"
        onClick={() => {
          onClose();
          onOpenShortcuts();
        }}
      />
      <Row
        icon={<UserIcon size={18} />}
        label="Account"
        value={me ? formatPhone(me.phone_number) : ""}
        onClick={() => {
          onClose();
          onOpenProfile();
        }}
      />

      <div className="my-2 h-px" style={{ background: "var(--sig-border)" }} />

      {placeholders.map((item) => (
        <Row
          key={item.label}
          icon={item.icon}
          label={item.label}
          value="Coming soon"
          onClick={() => toast(`${item.label} is coming soon`)}
        />
      ))}

      <div className="my-2 h-px" style={{ background: "var(--sig-border)" }} />

      <Row
        icon={<LeaveIcon size={18} />}
        label="Sign out"
        danger
        onClick={() => {
          void signOut().then(() => router.replace("/login"));
        }}
      />

      <p className="py-4 text-center text-[12px] leading-relaxed text-sig-text-3">
        Signal clone · v1.0.0
        <br />
        Encryption is mocked for this build.
      </p>
    </Modal>
  );
}

function Row({
  icon,
  label,
  value,
  onClick,
  danger = false,
}: {
  icon: React.ReactNode;
  label: string;
  value?: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left transition-colors hover:bg-sig-hover ${
        danger ? "text-sig-danger" : "text-sig-text"
      }`}
    >
      <span className={danger ? "text-sig-danger" : "text-sig-text-2"}>{icon}</span>
      <span className="flex-1 text-[14.5px]">{label}</span>
      {value && <span className="text-[13px] text-sig-text-3">{value}</span>}
    </button>
  );
}
