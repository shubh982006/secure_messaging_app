"use client";

import { useEffect, useRef, useState } from "react";

import { mediaUrl } from "@/lib/api";
import type { Attachment } from "@/lib/types";
import { PauseIcon, PlayIcon } from "@/components/icons";

/** Deterministic bars from the URL: a real waveform needs decoded audio, and
 *  decoding every clip on render costs more than it communicates. */
function barsFor(seed: string, count = 34): number[] {
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  return Array.from({ length: count }, (_, index) => {
    hash = (hash * 1103515245 + 12345) >>> 0;
    const value = (hash % 100) / 100;
    // Taper the ends so it reads as speech rather than noise.
    const taper = Math.sin((index / (count - 1)) * Math.PI) * 0.55 + 0.45;
    return Math.max(0.18, value * taper);
  });
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

export function VoiceMessage({
  attachment,
  outgoing,
}: {
  attachment: Attachment;
  outgoing: boolean;
}) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [duration, setDuration] = useState(0);

  const bars = barsFor(attachment.url);

  useEffect(() => {
    const element = audio.current;
    if (!element) return;
    const onTime = () => setProgress(element.currentTime);
    const onMeta = () => {
      // A webm/opus blob from MediaRecorder often reports Infinity until it is
      // seeked to the end, which is the well-known duration bug.
      if (Number.isFinite(element.duration)) setDuration(element.duration);
    };
    const onEnd = () => {
      setPlaying(false);
      setProgress(0);
    };
    element.addEventListener("timeupdate", onTime);
    element.addEventListener("loadedmetadata", onMeta);
    element.addEventListener("durationchange", onMeta);
    element.addEventListener("ended", onEnd);
    return () => {
      element.removeEventListener("timeupdate", onTime);
      element.removeEventListener("loadedmetadata", onMeta);
      element.removeEventListener("durationchange", onMeta);
      element.removeEventListener("ended", onEnd);
    };
  }, []);

  function toggle() {
    const element = audio.current;
    if (!element) return;
    if (playing) {
      element.pause();
      setPlaying(false);
    } else {
      void element.play();
      setPlaying(true);
    }
  }

  function seekTo(fraction: number) {
    const element = audio.current;
    if (!element || !duration) return;
    element.currentTime = fraction * duration;
    setProgress(element.currentTime);
  }

  const played = duration ? progress / duration : 0;
  const accent = outgoing ? "#ffffff" : "var(--color-ultramarine-light)";
  const idle = outgoing ? "rgba(255,255,255,0.4)" : "var(--sig-text-3)";

  return (
    <div className="flex min-w-[210px] items-center gap-2.5 py-0.5">
      <audio ref={audio} src={mediaUrl(attachment.url)} preload="metadata" />
      <button
        onClick={toggle}
        aria-label={playing ? "Pause voice message" : "Play voice message"}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition-opacity hover:opacity-85"
        style={{
          background: outgoing ? "rgba(255,255,255,0.22)" : "var(--sig-hover)",
          color: outgoing ? "#fff" : "var(--sig-text)",
        }}
      >
        {playing ? <PauseIcon size={16} /> : <PlayIcon size={16} />}
      </button>

      <button
        className="flex h-8 flex-1 items-center gap-[2px]"
        aria-label="Seek"
        onClick={(event) => {
          const box = event.currentTarget.getBoundingClientRect();
          seekTo(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)));
        }}
      >
        {bars.map((height, index) => (
          <span
            key={index}
            className="flex-1 rounded-full transition-colors"
            style={{
              height: `${Math.round(height * 100)}%`,
              minWidth: 2,
              background: index / bars.length <= played ? accent : idle,
            }}
          />
        ))}
      </button>

      <span
        className="w-9 shrink-0 text-right text-[11.5px] tabular-nums"
        style={{ color: outgoing ? "rgba(255,255,255,0.75)" : "var(--sig-text-3)" }}
      >
        {formatDuration(playing || progress ? duration - progress : duration)}
      </span>
    </div>
  );
}
