"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { formatPhone } from "@/lib/format";
import { useStore } from "@/lib/store";
import { Avatar } from "@/components/Avatar";
import { Modal, PrimaryButton } from "@/components/Modal";
import { CloseIcon, ImageIcon } from "@/components/icons";

export function ProfileModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const me = useStore((state) => state.me);
  const setMe = useStore((state) => state.setMe);
  const toast = useStore((state) => state.toast);

  const [displayName, setDisplayName] = useState("");
  const [about, setAbout] = useState("");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const filePicker = useRef<HTMLInputElement>(null);

  /**
   * Reuses the same /attachments endpoint messages use, so there is one upload
   * path in the app. What lands in avatar_url is the returned relative path -
   * Avatar resolves it against the API host, so the stored value stays correct
   * even if that host changes between environments.
   */
  async function pickAvatar(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (!file.type.startsWith("image/")) {
      setError("Choose an image file");
      return;
    }
    // Mirrors settings.max_upload_bytes so the user is told before the round trip.
    if (file.size > 10 * 1024 * 1024) {
      setError("Images must be 10MB or smaller");
      return;
    }
    setUploading(true);
    try {
      const uploaded = await api.uploadAttachment(file);
      setAvatarUrl(uploaded.url);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not upload that image");
    } finally {
      setUploading(false);
      // Let the same file be re-picked after a failure.
      if (filePicker.current) filePicker.current.value = "";
    }
  }

  useEffect(() => {
    if (!open || !me) return;
    setDisplayName(me.display_name ?? "");
    setAbout(me.about ?? "");
    setAvatarUrl(me.avatar_url ?? "");
    setUploading(false);
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
        <input
          ref={filePicker}
          type="file"
          accept="image/*"
          hidden
          onChange={(event) => void pickAvatar(event.target.files?.[0])}
        />

        <div className="group relative">
          <button
            type="button"
            onClick={() => filePicker.current?.click()}
            disabled={uploading}
            aria-label="Change profile photo"
            className="focus-ring block rounded-full"
          >
            <Avatar
              name={displayName || me.display_name}
              src={avatarUrl}
              seed={me.id}
              size={92}
            />
            {/* Signal dims the photo and shows a camera affordance on hover. */}
            <span
              className={`absolute inset-0 flex items-center justify-center rounded-full text-white transition-opacity ${
                uploading ? "opacity-100" : "opacity-0 group-hover:opacity-100"
              }`}
              style={{ background: "rgba(0,0,0,0.5)" }}
            >
              {uploading ? (
                <span className="text-[12px] font-medium">Uploading…</span>
              ) : (
                <ImageIcon size={24} />
              )}
            </span>
          </button>

          {avatarUrl && !uploading && (
            <button
              type="button"
              onClick={() => setAvatarUrl("")}
              aria-label="Remove profile photo"
              title="Remove photo"
              className="focus-ring absolute -right-1 bottom-0 flex h-7 w-7 items-center justify-center rounded-full border text-sig-text-2 transition-colors hover:text-sig-text"
              style={{
                background: "var(--sig-elevated)",
                borderColor: "var(--sig-border)",
              }}
            >
              <CloseIcon size={14} />
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={() => filePicker.current?.click()}
          disabled={uploading}
          className="focus-ring mt-2.5 rounded-full px-3 py-1 text-[13.5px] font-medium text-ultramarine-light transition-colors hover:bg-sig-hover disabled:opacity-50"
        >
          {avatarUrl ? "Change photo" : "Upload photo"}
        </button>

        <p className="mt-1.5 text-[13px] text-sig-text-3">
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

      <Field
        label="Or paste an image link"
        hint="Leave blank to fall back to your initials."
      >
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
