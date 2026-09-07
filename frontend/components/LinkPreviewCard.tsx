"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { LinkPreview } from "@/lib/types";

// Deliberately conservative: only unfurl what unambiguously looks like a URL.
const URL_PATTERN = /https?:\/\/[^\s<>"']+/i;

/** Module-level so switching conversations does not refetch the same card. */
const cache = new Map<string, LinkPreview | null>();

export function firstUrl(text: string | null | undefined): string | null {
  if (!text) return null;
  const match = text.match(URL_PATTERN);
  return match ? match[0].replace(/[.,;:!?)\]]+$/, "") : null;
}

export function LinkPreviewCard({
  url,
  outgoing,
}: {
  url: string;
  outgoing: boolean;
}) {
  const [preview, setPreview] = useState<LinkPreview | null | undefined>(
    cache.has(url) ? cache.get(url) : undefined,
  );

  useEffect(() => {
    if (cache.has(url)) {
      setPreview(cache.get(url));
      return;
    }
    let cancelled = false;
    api
      .linkPreview(url)
      .then((result) => {
        cache.set(url, result);
        if (!cancelled) setPreview(result);
      })
      .catch(() => {
        // A link that cannot be unfurled (private host, 404, not HTML) just
        // renders as plain text - never as a broken card.
        cache.set(url, null);
        if (!cancelled) setPreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [url]);

  if (!preview || (!preview.title && !preview.description && !preview.image)) {
    return null;
  }

  return (
    <a
      href={preview.url}
      target="_blank"
      rel="noreferrer noopener"
      className="mb-1.5 block overflow-hidden rounded-xl transition-opacity hover:opacity-90"
      style={{
        background: outgoing ? "rgba(255,255,255,0.14)" : "rgba(255,255,255,0.06)",
      }}
    >
      {preview.image && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={preview.image}
          alt=""
          loading="lazy"
          className="h-32 w-full object-cover"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      )}
      <span className="block px-2.5 py-2">
        {preview.site_name && (
          <span
            className={`block text-[11px] uppercase tracking-wide ${
              outgoing ? "text-white/65" : "text-sig-text-3"
            }`}
          >
            {preview.site_name}
          </span>
        )}
        {preview.title && (
          <span className="mt-0.5 line-clamp-2 block text-[13.5px] font-semibold">
            {preview.title}
          </span>
        )}
        {preview.description && (
          <span
            className={`mt-0.5 line-clamp-2 block text-[12.5px] ${
              outgoing ? "text-white/75" : "text-sig-text-2"
            }`}
          >
            {preview.description}
          </span>
        )}
      </span>
    </a>
  );
}

/** Renders message text with any URLs as real links. */
export function LinkifiedText({ text, outgoing }: { text: string; outgoing: boolean }) {
  const parts = text.split(/(https?:\/\/[^\s<>"']+)/gi);
  return (
    <>
      {parts.map((part, index) =>
        /^https?:\/\//i.test(part) ? (
          <a
            key={index}
            href={part}
            target="_blank"
            rel="noreferrer noopener"
            onClick={(event) => event.stopPropagation()}
            className="underline underline-offset-2 hover:opacity-80"
            style={{ color: outgoing ? "#ffffff" : "var(--color-ultramarine-light)" }}
          >
            {part}
          </a>
        ) : (
          part
        ),
      )}
    </>
  );
}
