"use client";

import { useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatPhone } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Avatar } from "@/components/Avatar";
import { Modal, PrimaryButton } from "@/components/Modal";

export function ProfileModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const me = useStore((state) => state.me);
  const setMe = useStore((state) => state.setMe);
  const toast = useStore((state) => state.toast);

  const [displayName, setDisplayName] = useState("");
  const [about, setAbout] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !me) return;
    setDisplayName(me.display_name ?? "");
    setAbout(me.about ?? "");
    setAvatarUrl(me.avatar_url ?? "");
    setError(null);
  }, [open, me]);

  if (!me) return null;

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const updated = await api.updateProfile({
        display_name: displayName.trim(),
        about: about.trim(),
        avatar_url: avatarUrl.trim() || null,
      });
      setMe(updated);
      toast("Profile updated");
      onClose();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not save your profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      open={open}
      title="Profile"
      onClose={onClose}
      footer={
        <div className="flex justify-end gap-2">
          <PrimaryButton tone="ghost" onClick={onClose}>
            Cancel
          </PrimaryButton>
          <PrimaryButton disabled={busy || !displayName.trim()} onClick={() => void save()}>
            {busy ? "Saving…" : "Save"}
          </PrimaryButton>
        </div>
      }
    >
      <div className="flex flex-col items-center pb-5 pt-1">
        <Avatar
          name={displayName || me.display_name}
          src={avatarUrl || me.avatar_url}
          seed={me.id}
          size={92}
        />
        <p className="mt-3 text-[13px] text-sig-text-3">
          {formatPhone(me.phone_number)}
        </p>
      </div>

      <Field label="Your name">
        <input
          value={displayName}
          onChange={(event) => setDisplayName(event.target.value)}
          maxLength={60}
          className="focus-ring w-full rounded-lg bg-sig-input px-3.5 py-2.5 text-[15px] text-sig-text"
        />
      </Field>

      <Field label="About">
        <input
          value={about}
          onChange={(event) => setAbout(event.target.value)}
          maxLength={100}
          placeholder="On Signal"
          className="focus-ring w-full rounded-lg bg-sig-input px-3.5 py-2.5 text-[15px] text-sig-text placeholder:text-sig-text-3"
        />
      </Field>

      <Field label="Avatar URL" hint="Paste an image link, or leave it blank for initials.">
        <input
          value={avatarUrl}
          onChange={(event) => setAvatarUrl(event.target.value)}
          placeholder="https://…"
          className="focus-ring w-full rounded-lg bg-sig-input px-3.5 py-2.5 text-[15px] text-sig-text placeholder:text-sig-text-3"
        />
      </Field>

      {error && <p className="pb-2 text-[13px] text-sig-danger">{error}</p>}
    </Modal>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="mb-4 block">
      <span className="mb-1.5 block text-[12px] font-medium uppercase tracking-wider text-sig-text-3">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1.5 block text-[12px] text-sig-text-3">{hint}</span>}
    </label>
  );
}
