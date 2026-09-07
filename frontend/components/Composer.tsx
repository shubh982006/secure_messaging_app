"use client";

import { useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { useStore } from "@/lib/store";
import type { Attachment, Message } from "@/lib/types";
import { ComposerAttachments } from "@/components/Attachments";
import {
  AttachIcon,
  CloseIcon,
  EmojiIcon,
  ImageIcon,
  MicIcon,
  PlusIcon,
  SendIcon,
  TimerIcon,
} from "@/components/icons";

const EMOJI = [
  "😀", "😃", "😄", "😁", "😆", "😅", "🤣", "😂", "🙂", "🙃",
  "😉", "😊", "😍", "🥰", "😘", "😎", "🤔", "🤗", "🤩", "🥳",
  "😢", "😭", "😤", "😱", "🤯", "😴", "👍", "👎", "👏", "🙏",
  "💪", "🔥", "✨", "🎉", "❤️", "🧡", "💛", "💚", "💙", "💜",
];

const MAX_ATTACHMENTS = 6;

interface StagedFile {
  id: string;
  file: File;
  preview: string | null;
  uploading: boolean;
}

interface Props {
  conversationId: string;
  replyTo: Message | null;
  replyToName: string | null;
  onCancelReply: () => void;
  disappearSeconds: number;
  /** Files dropped onto the chat pane are handed down to the composer. */
  droppedFiles?: File[];
  onDroppedFilesHandled?: () => void;
}

/** Signal's composer: attach, a rounded input with emoji inside, then send. */
export function Composer({
  conversationId,
  replyTo,
  replyToName,
  onCancelReply,
  disappearSeconds,
  droppedFiles,
  onDroppedFilesHandled,
}: Props) {
  const sendMessage = useStore((state) => state.sendMessage);
  const setTyping = useStore((state) => state.setTyping);
  const toast = useStore((state) => state.toast);

  const [text, setText] = useState("");
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [sending, setSending] = useState(false);

  const textarea = useRef<HTMLTextAreaElement>(null);
  const filePicker = useRef<HTMLInputElement>(null);
  const imagePicker = useRef<HTMLInputElement>(null);
  const typingSince = useRef(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setText("");
    setEmojiOpen(false);
    setStaged((current) => {
      current.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
      return [];
    });
  }, [conversationId]);

  useEffect(() => {
    if (replyTo) textarea.current?.focus();
  }, [replyTo]);

  useEffect(() => {
    return () => {
      if (typingTimer.current) clearTimeout(typingTimer.current);
    };
  }, []);

  function stageFiles(files: FileList | File[] | null) {
    if (!files) return;
    const incoming = Array.from(files);
    if (!incoming.length) return;

    setStaged((current) => {
      const room = MAX_ATTACHMENTS - current.length;
      if (room <= 0) {
        toast(`You can attach up to ${MAX_ATTACHMENTS} files`, "error");
        return current;
      }
      if (incoming.length > room) toast(`Only the first ${room} file(s) were added`);
      return [
        ...current,
        ...incoming.slice(0, room).map((file) => ({
          id: crypto.randomUUID(),
          file,
          preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
          uploading: false,
        })),
      ];
    });
    textarea.current?.focus();
  }

  // Files dropped anywhere on the chat pane arrive here.
  useEffect(() => {
    if (droppedFiles?.length) {
      stageFiles(droppedFiles);
      onDroppedFilesHandled?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [droppedFiles]);

  function removeStaged(id: string) {
    setStaged((current) => {
      const target = current.find((item) => item.id === id);
      if (target?.preview) URL.revokeObjectURL(target.preview);
      return current.filter((item) => item.id !== id);
    });
  }

  function announceTyping() {
    if (!typingSince.current) {
      typingSince.current = true;
      setTyping(conversationId, true);
    }
    if (typingTimer.current) clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => {
      typingSince.current = false;
      setTyping(conversationId, false);
    }, 2500);
  }

  function stopTyping() {
    if (typingTimer.current) clearTimeout(typingTimer.current);
    if (typingSince.current) {
      typingSince.current = false;
      setTyping(conversationId, false);
    }
  }

  async function submit() {
    const body = text.trim();
    if ((!body && staged.length === 0) || sending) return;

    setSending(true);
    let attachments: Attachment[] = [];

    try {
      if (staged.length) {
        setStaged((current) => current.map((item) => ({ ...item, uploading: true })));
        // Upload first, then send one message referencing the stored URLs.
        const uploaded = await Promise.all(
          staged.map((item) => api.uploadAttachment(item.file)),
        );
        attachments = uploaded.map(({ kind: _kind, ...attachment }) => attachment);
      }
    } catch (caught) {
      setStaged((current) => current.map((item) => ({ ...item, uploading: false })));
      setSending(false);
      toast(
        caught instanceof ApiError ? caught.message : "Could not upload that file",
        "error",
      );
      return;
    }

    sendMessage(conversationId, body, replyTo?.id ?? null, attachments);

    staged.forEach((item) => item.preview && URL.revokeObjectURL(item.preview));
    setStaged([]);
    setText("");
    setEmojiOpen(false);
    setSending(false);
    onCancelReply();
    stopTyping();
    textarea.current?.focus();
  }

  const canSend = (text.trim().length > 0 || staged.length > 0) && !sending;

  return (
    <div
      className="relative border-t px-3 py-2.5"
      style={{ borderColor: "var(--sig-border)", background: "var(--sig-bg)" }}
    >
      <input
        ref={filePicker}
        type="file"
        multiple
        hidden
        onChange={(event) => {
          stageFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <input
        ref={imagePicker}
        type="file"
        accept="image/*"
        multiple
        hidden
        onChange={(event) => {
          stageFiles(event.target.files);
          event.target.value = "";
        }}
      />

      {replyTo && (
        <div
          className="animate-fade-up mb-2 flex items-center gap-2 rounded-lg px-3 py-2"
          style={{ background: "var(--sig-hover)" }}
        >
          <span className="w-[3px] shrink-0 self-stretch rounded-full bg-ultramarine-light" />
          <span className="min-w-0 flex-1">
            <span className="block text-[12.5px] font-semibold text-ultramarine-light">
              Replying to {replyToName ?? "message"}
            </span>
            <span className="block truncate text-[13px] text-sig-text-2">
              {replyTo.content || (replyTo.type === "image" ? "Photo" : "Attachment")}
            </span>
          </span>
          <button
            onClick={onCancelReply}
            aria-label="Cancel reply"
            className="rounded-full p-1 text-sig-text-3 hover:text-sig-text"
          >
            <CloseIcon size={15} />
          </button>
        </div>
      )}

      <ComposerAttachments items={staged} onRemove={removeStaged} />

      {emojiOpen && (
        <div
          className="animate-pop absolute bottom-full left-3 mb-2 grid w-[280px] grid-cols-10 gap-0.5 rounded-xl border p-2"
          style={{
            background: "var(--sig-elevated)",
            borderColor: "var(--sig-border)",
            boxShadow: "var(--sig-shadow)",
          }}
        >
          {EMOJI.map((emoji) => (
            <button
              key={emoji}
              onClick={() => {
                setText((current) => current + emoji);
                textarea.current?.focus();
              }}
              className="rounded p-0.5 text-[17px] transition-transform hover:scale-125"
            >
              {emoji}
            </button>
          ))}
        </div>
      )}

      <div className="flex items-end gap-2">
        <button
          onClick={() => filePicker.current?.click()}
          aria-label="Attach a file"
          title="Attach a file"
          className="focus-ring mb-[3px] flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text"
        >
          <PlusIcon size={21} />
        </button>

        <div
          className="flex min-h-[38px] flex-1 items-end gap-1.5 rounded-[19px] px-3 py-1.5"
          style={{ background: "var(--sig-input)" }}
        >
          {disappearSeconds > 0 && (
            <TimerIcon
              size={16}
              className="mb-1.5 shrink-0 text-ultramarine-light"
              // Explains why the composer looks different in this thread.
            />
          )}
          <textarea
            ref={textarea}
            value={text}
            rows={1}
            onChange={(event) => {
              setText(event.target.value);
              if (event.target.value.trim()) announceTyping();
              else stopTyping();
            }}
            onBlur={stopTyping}
            onPaste={(event) => {
              // Pasting a screenshot attaches it, like Signal Desktop.
              const files = Array.from(event.clipboardData.files);
              if (files.length) {
                event.preventDefault();
                stageFiles(files);
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder={disappearSeconds > 0 ? "Disappearing message" : "Message"}
            aria-label="Message"
            className="sig-scroll max-h-[140px] min-h-[24px] flex-1 resize-none self-center bg-transparent py-1 text-[14.5px] leading-[1.4] text-sig-text placeholder:text-sig-text-3"
          />

          <button
            onClick={() => setEmojiOpen((open) => !open)}
            aria-label="Emoji"
            title="Emoji"
            className="focus-ring mb-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:text-sig-text"
          >
            <EmojiIcon size={19} />
          </button>
          <button
            onClick={() => imagePicker.current?.click()}
            aria-label="Attach a photo"
            title="Attach a photo"
            className="focus-ring mb-1 hidden h-7 w-7 shrink-0 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:text-sig-text sm:flex"
          >
            <ImageIcon size={17} />
          </button>
          <button
            onClick={() => filePicker.current?.click()}
            aria-label="Attach a document"
            title="Attach a document"
            className="focus-ring mb-1 hidden h-7 w-7 shrink-0 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:text-sig-text sm:flex"
          >
            <AttachIcon size={17} />
          </button>
        </div>

        {canSend ? (
          <button
            onClick={() => void submit()}
            aria-label="Send"
            title="Send"
            className="focus-ring mb-[3px] flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ultramarine text-white transition-colors hover:bg-ultramarine-hover"
          >
            <SendIcon size={19} />
          </button>
        ) : (
          <button
            onClick={() => toast("Voice messages are coming soon")}
            aria-label="Record voice message"
            title="Record voice message"
            disabled={sending}
            className="focus-ring mb-[3px] flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text disabled:opacity-40"
          >
            <MicIcon size={19} />
          </button>
        )}
      </div>
    </div>
  );
}
