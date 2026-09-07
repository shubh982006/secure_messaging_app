"use client";

import { useEffect, useState } from "react";

import { mediaUrl } from "@/lib/api";
import type { Attachment } from "@/lib/types";
import { CloseIcon, DownloadIcon, FileIcon } from "@/components/icons";

export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes) return "";
  const units = ["B", "KB", "MB", "GB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value < 10 && unit > 0 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export function isImage(attachment: Attachment): boolean {
  return (attachment.mime_type ?? "").startsWith("image/");
}

/** Attachments rendered inside a message bubble. */
export function MessageAttachments({
  attachments,
  outgoing,
  onOpenImage,
}: {
  attachments: Attachment[];
  outgoing: boolean;
  onOpenImage: (attachment: Attachment) => void;
}) {
  if (!attachments.length) return null;

  const images = attachments.filter(isImage);
  const files = attachments.filter((attachment) => !isImage(attachment));

  return (
    <div className="mb-1 flex flex-col gap-1.5">
      {images.length > 0 && (
        <div
          className={`grid gap-1 ${images.length > 1 ? "grid-cols-2" : "grid-cols-1"}`}
        >
          {images.map((attachment, index) => {
            // Keep the bubble from jumping while the image loads.
            const ratio =
              attachment.width && attachment.height
                ? attachment.width / attachment.height
                : 4 / 3;
            const single = images.length === 1;
            return (
              <button
                key={`${attachment.url}-${index}`}
                onClick={() => onOpenImage(attachment)}
                className="overflow-hidden rounded-xl"
                style={{
                  aspectRatio: single ? String(ratio) : "1 / 1",
                  maxHeight: single ? 320 : 160,
                  // Never upscale a large photo past the bubble, but keep a
                  // tiny image big enough to see and tap.
                  width:
                    single && attachment.width
                      ? Math.min(Math.max(attachment.width, 140), 320)
                      : "100%",
                  background: "rgba(0,0,0,0.2)",
                }}
                aria-label={`Open ${attachment.name ?? "image"}`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={mediaUrl(attachment.url)}
                  alt={attachment.name ?? "Attachment"}
                  loading="lazy"
                  className="h-full w-full object-cover transition-transform hover:scale-[1.02]"
                />
              </button>
            );
          })}
        </div>
      )}

      {files.map((attachment, index) => (
        <a
          key={`${attachment.url}-${index}`}
          href={mediaUrl(attachment.url)}
          target="_blank"
          rel="noreferrer"
          download={attachment.name ?? undefined}
          className="flex items-center gap-2.5 rounded-xl px-2.5 py-2 transition-opacity hover:opacity-85"
          style={{
            background: outgoing ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.07)",
          }}
        >
          <span
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
            style={{ background: outgoing ? "rgba(255,255,255,0.2)" : "var(--sig-hover)" }}
          >
            <FileIcon size={17} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13.5px] font-medium">
              {attachment.name ?? "Attachment"}
            </span>
            <span className={`block text-[11.5px] ${outgoing ? "text-white/70" : "text-sig-text-3"}`}>
              {formatBytes(attachment.size_bytes)}
            </span>
          </span>
          <DownloadIcon size={16} className={outgoing ? "text-white/80" : "text-sig-text-3"} />
        </a>
      ))}
    </div>
  );
}

/** Full-screen image viewer, dismissed with Escape or a click outside. */
export function Lightbox({
  attachment,
  onClose,
}: {
  attachment: Attachment | null;
  onClose: () => void;
}) {
  useEffect(() => {
    if (!attachment) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [attachment, onClose]);

  if (!attachment) return null;

  return (
    <div
      className="fixed inset-0 z-[70] flex flex-col bg-black/90"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={attachment.name ?? "Image"}
    >
      <div className="flex items-center justify-between px-4 py-3 text-white">
        <span className="truncate text-[14px]">{attachment.name ?? "Image"}</span>
        <div className="flex items-center gap-1">
          <a
            href={mediaUrl(attachment.url)}
            download={attachment.name ?? undefined}
            onClick={(event) => event.stopPropagation()}
            className="rounded-full p-2 transition-colors hover:bg-white/15"
            aria-label="Download"
          >
            <DownloadIcon size={19} />
          </a>
          <button
            onClick={onClose}
            className="rounded-full p-2 transition-colors hover:bg-white/15"
            aria-label="Close"
          >
            <CloseIcon size={19} />
          </button>
        </div>
      </div>
      <div className="flex flex-1 items-center justify-center overflow-hidden p-4">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={mediaUrl(attachment.url)}
          alt={attachment.name ?? "Attachment"}
          onClick={(event) => event.stopPropagation()}
          className="max-h-full max-w-full rounded-lg object-contain"
        />
      </div>
    </div>
  );
}

/** Thumbnails of files staged in the composer, before sending. */
export function ComposerAttachments({
  items,
  onRemove,
}: {
  items: { id: string; file: File; preview: string | null; uploading: boolean }[];
  onRemove: (id: string) => void;
}) {
  if (!items.length) return null;

  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {items.map((item) => (
        <div
          key={item.id}
          className="relative flex items-center gap-2 rounded-lg border p-1.5 pr-2"
          style={{ borderColor: "var(--sig-border)", background: "var(--sig-hover)" }}
        >
          {item.preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={item.preview}
              alt={item.file.name}
              className="h-10 w-10 rounded object-cover"
            />
          ) : (
            <span className="flex h-10 w-10 items-center justify-center rounded bg-sig-active text-sig-text-2">
              <FileIcon size={17} />
            </span>
          )}
          <span className="max-w-[150px]">
            <span className="block truncate text-[12.5px] text-sig-text">{item.file.name}</span>
            <span className="block text-[11px] text-sig-text-3">
              {item.uploading ? "Uploading…" : formatBytes(item.file.size)}
            </span>
          </span>
          <button
            onClick={() => onRemove(item.id)}
            aria-label={`Remove ${item.file.name}`}
            className="ml-1 rounded-full p-1 text-sig-text-3 transition-colors hover:bg-sig-active hover:text-sig-text"
          >
            <CloseIcon size={13} />
          </button>
        </div>
      ))}
    </div>
  );
}
