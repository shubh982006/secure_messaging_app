"use client";

import { mediaUrl } from "@/lib/api";
import { avatarColor, initials } from "@/lib/format";
import { GroupIcon } from "./icons";

interface AvatarProps {
  name: string | null | undefined;
  src?: string | null;
  seed?: string | null;
  size?: number;
  isGroup?: boolean;
  online?: boolean;
  className?: string;
}

/**
 * Signal renders an initials avatar on a stable per-contact colour when no
 * photo is set, and a group glyph for groups.
 */
export function Avatar({
  name,
  src,
  seed,
  size = 48,
  isGroup = false,
  online = false,
  className = "",
}: AvatarProps) {
  const background = avatarColor(seed ?? name);
  const fontSize = Math.round(size * 0.38);

  return (
    <span
      className={`relative inline-flex shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      {src ? (
        // An uploaded avatar comes back as a path relative to the API host
        // ("/media/…"), which would otherwise resolve against the web origin
        // and 404. mediaUrl passes absolute URLs (a pasted link) through.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={mediaUrl(src)}
          alt={name ?? "Avatar"}
          className="h-full w-full rounded-full object-cover"
          style={{ width: size, height: size }}
        />
      ) : (
        <span
          className="flex h-full w-full select-none items-center justify-center rounded-full font-medium text-white"
          style={{ background: isGroup ? "var(--sig-border)" : background, fontSize }}
          aria-hidden
        >
          {isGroup ? (
            <GroupIcon size={Math.round(size * 0.52)} className="text-sig-text-2" />
          ) : (
            initials(name)
          )}
        </span>
      )}

      {online && (
        <span
          className="absolute bottom-0 right-0 rounded-full border-2"
          style={{
            width: Math.max(10, size * 0.24),
            height: Math.max(10, size * 0.24),
            background: "#3ecf6e",
            borderColor: "var(--sig-pane)",
          }}
          aria-label="Online"
        />
      )}
    </span>
  );
}
