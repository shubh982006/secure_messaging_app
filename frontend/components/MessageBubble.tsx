"use client";

import { memo, useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";

import { timeOfDay } from "@/lib/format";
import type { Attachment, Message } from "@/lib/types";
import { Avatar } from "@/components/Avatar";
import { MessageAttachments } from "@/components/Attachments";
import { LinkPreviewCard, LinkifiedText, firstUrl } from "@/components/LinkPreviewCard";
import { VoiceMessage } from "@/components/VoiceMessage";
import {
  ChevronDownIcon,
  CopyIcon,
  EmojiIcon,
  ForwardIcon,
  ReplyIcon,
  StatusTick,
  TimerIcon,
  TrashIcon,
} from "@/components/icons";

const QUICK_REACTIONS = ["👍", "❤️", "😂", "😮", "😢", "🙏"];

/** Revealed by the "+" on the quick bar, the way WhatsApp expands to a grid. */
const MORE_REACTIONS = [
  "😀", "😅", "🥹", "😍", "😘", "🤗", "🤔", "😐",
  "🙄", "😴", "😭", "😤", "😡", "🥳", "🤯", "😎",
  "👏", "🙌", "💪", "🔥", "✅", "💯", "🎉", "👀",
];

type Anchor = { left: number; top: number; flipX: boolean; flipY: boolean };

/** Room a popover needs on a side before it will open toward it. */
const POPOVER_CLEARANCE_PX = 240;

/** How long a touch must rest on a bubble before the reaction bar opens. */
const LONG_PRESS_MS = 450;
/** Past this much finger travel the gesture is a scroll, not a press. */
const LONG_PRESS_SLOP_PX = 10;

export interface BubbleProps {
  message: Message;
  outgoing: boolean;
  isGroup: boolean;
  senderName: string | null;
  senderAvatar: string | null;
  /** First message of a run by the same author - shows the name + avatar. */
  startsGroup: boolean;
  /** Last message of a run - carries the tail and the timestamp. */
  endsGroup: boolean;
  meId: string;
  onReply: (message: Message) => void;
  onForward: (message: Message) => void;
  onDelete: (message: Message) => void;
  onReact: (message: Message, emoji: string) => void;
  onCopy: (text: string) => void;
  onOpenImage: (attachment: Attachment) => void;
}

function MessageBubbleBase({
  message,
  outgoing,
  isGroup,
  senderName,
  senderAvatar,
  startsGroup,
  endsGroup,
  meId,
  onReply,
  onForward,
  onDelete,
  onReact,
  onCopy,
  onOpenImage,
}: BubbleProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const [reactionsOpen, setReactionsOpen] = useState(false);
  const [pickerExpanded, setPickerExpanded] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);
  const bubble = useRef<HTMLDivElement>(null);
  const chevron = useRef<HTMLButtonElement>(null);
  // Portalled popovers live outside `wrapper`, so the outside-click check has
  // to know about them or the first click inside would dismiss them.
  const menuBox = useRef<HTMLDivElement>(null);
  const pickerBox = useRef<HTMLDivElement>(null);
  const [menuAnchor, setMenuAnchor] = useState<Anchor | null>(null);
  const [pickerAnchor, setPickerAnchor] = useState<Anchor | null>(null);
  const pressTimer = useRef<number | null>(null);
  const pressOrigin = useRef<{ x: number; y: number } | null>(null);

  function cancelPress() {
    if (pressTimer.current !== null) {
      window.clearTimeout(pressTimer.current);
      pressTimer.current = null;
    }
    pressOrigin.current = null;
  }

  /** Long-press is the touch equivalent of the hover toolbar's React button. */
  function beginPress(event: ReactPointerEvent) {
    if (event.pointerType !== "touch") return;
    cancelPress();
    pressOrigin.current = { x: event.clientX, y: event.clientY };
    pressTimer.current = window.setTimeout(() => {
      pressTimer.current = null;
      openPicker();
      // Otherwise the browser starts selecting the message text underneath.
      window.getSelection?.()?.removeAllRanges();
    }, LONG_PRESS_MS);
  }

  /** A finger that travels is scrolling the thread, so abandon the press. */
  function trackPress(event: ReactPointerEvent) {
    const origin = pressOrigin.current;
    if (!origin) return;
    if (
      Math.abs(event.clientX - origin.x) > LONG_PRESS_SLOP_PX ||
      Math.abs(event.clientY - origin.y) > LONG_PRESS_SLOP_PX
    ) {
      cancelPress();
    }
  }

  /**
   * The thread scroller is `overflow-y: auto`, so it clips any absolutely
   * positioned descendant that leaves its box - which is why the menu showed
   * up as a sliver under the last bubble. Both popovers are portalled to
   * <body> and placed from their anchor's viewport rect instead.
   *
   * Placement uses translate rather than a measured width so it stays correct
   * as the picker grows: `left` is the edge to align to, and the flips pull the
   * box back over it. The transform lives on an outer wrapper because
   * `animate-pop` animates `transform: scale()` and would otherwise clobber it.
   */
  function anchorTo(element: HTMLElement | null, preferAbove: boolean, gap: number) {
    if (!element) return null;
    const rect = element.getBoundingClientRect();
    const roomAbove = rect.top > POPOVER_CLEARANCE_PX;
    const roomBelow = window.innerHeight - rect.bottom > POPOVER_CLEARANCE_PX;
    const above = preferAbove ? roomAbove : !roomBelow && roomAbove;
    return {
      left: outgoing ? rect.right : rect.left,
      top: above ? rect.top - gap : rect.bottom + gap,
      flipX: outgoing,
      flipY: above,
    };
  }

  function openMenu() {
    setReactionsOpen(false);
    setMenuAnchor(anchorTo(chevron.current, false, 4));
    setMenuOpen(true);
  }

  function openPicker() {
    setMenuOpen(false);
    setPickerExpanded(false);
    setPickerAnchor(anchorTo(bubble.current, true, 8));
    setReactionsOpen(true);
  }

  function react(emoji: string) {
    onReact(message, emoji);
    setReactionsOpen(false);
    setPickerExpanded(false);
  }

  // A bubble that unmounts mid-press must not fire its timer.
  useEffect(() => cancelPress, []);

  useEffect(() => {
    if (!menuOpen && !reactionsOpen) return;
    const onDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        wrapper.current?.contains(target) ||
        menuBox.current?.contains(target) ||
        pickerBox.current?.contains(target)
      ) {
        return;
      }
      setMenuOpen(false);
      setReactionsOpen(false);
      setPickerExpanded(false);
    };
    // A fixed popover cannot follow its anchor, so scrolling dismisses it.
    const onReflow = () => {
      setMenuOpen(false);
      setReactionsOpen(false);
      setPickerExpanded(false);
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("scroll", onReflow, true);
    window.addEventListener("resize", onReflow);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("scroll", onReflow, true);
      window.removeEventListener("resize", onReflow);
    };
  }, [menuOpen, reactionsOpen]);

  // --- system message: a centred grey line, like Signal's group events ------
  if (message.type === "system") {
    return (
      <div className="my-3 flex justify-center px-6">
        <span className="rounded-full bg-sig-hover px-3 py-1 text-center text-[12.5px] leading-snug text-sig-text-2">
          {message.content}
        </span>
      </div>
    );
  }

  const deleted = message.deleted_at !== null;

  // Signal squares off the corner on the "tail" side for every message in a run
  // except the last, which keeps the full radius.
  const corner = outgoing
    ? endsGroup
      ? "rounded-br-[18px]"
      : "rounded-br-[5px]"
    : endsGroup
      ? "rounded-bl-[18px]"
      : "rounded-bl-[5px]";

  // A voice note is an audio attachment with no caption - rendered as a player
  // rather than a file chip.
  const voiceNote =
    !deleted &&
    !message.content &&
    message.attachments.length === 1 &&
    (message.attachments[0].mime_type ?? "").startsWith("audio/")
      ? message.attachments[0]
      : null;

  const previewUrl =
    !deleted && !voiceNote && message.attachments.length === 0
      ? firstUrl(message.content)
      : null;

  const grouped = message.reactions.reduce<Record<string, string[]>>((acc, reaction) => {
    (acc[reaction.emoji] ??= []).push(reaction.user_id);
    return acc;
  }, {});

  return (
    <div
      ref={wrapper}
      className={`group/message relative flex w-full gap-2 px-4 ${
        outgoing ? "justify-end" : "justify-start"
      } ${endsGroup ? "mb-2" : "mb-[2px]"}`}
    >
      {/* Group chats show the sender's avatar beside the last message of a run. */}
      {!outgoing && isGroup && (
        <div className="w-7 shrink-0 self-end">
          {endsGroup && (
            <Avatar name={senderName} src={senderAvatar} seed={message.sender_id} size={28} />
          )}
        </div>
      )}

      <div
        className={`flex max-w-[min(560px,72%)] flex-col ${
          outgoing ? "items-end" : "items-start"
        }`}
      >
        <div
          ref={bubble}
          className={`relative rounded-[18px] px-3 py-[7px] ${corner} ${
            outgoing ? "text-white" : "text-sig-text"
          }`}
          style={{
            background: outgoing ? "var(--sig-bubble-out)" : "var(--sig-bubble-in)",
          }}
          onContextMenu={
            deleted
              ? undefined
              : (event) => {
                  event.preventDefault();
                  openPicker();
                }
          }
          onPointerDown={deleted ? undefined : beginPress}
          onPointerMove={deleted ? undefined : trackPress}
          onPointerUp={cancelPress}
          onPointerCancel={cancelPress}
          onPointerLeave={cancelPress}
        >
          {/* Sender name on the first message of a run, in that person's colour. */}
          {!outgoing && isGroup && startsGroup && (
            <p className="mb-0.5 text-[13px] font-semibold text-ultramarine-light">
              {senderName ?? "Unknown"}
            </p>
          )}

          {message.reply_to && !deleted && (
            <button
              onClick={() => {
                document
                  .getElementById(`message-${message.reply_to?.id}`)
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              className="mb-1.5 flex w-full gap-2 rounded-md px-2 py-1.5 text-left"
              style={{
                background: outgoing ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.07)",
              }}
            >
              <span
                className="w-[3px] shrink-0 rounded-full"
                style={{ background: outgoing ? "#ffffff" : "var(--color-ultramarine-light)" }}
              />
              <span className="min-w-0">
                <span
                  className={`block text-[12.5px] font-semibold ${
                    outgoing ? "text-white/90" : "text-ultramarine-light"
                  }`}
                >
                  {message.reply_to.sender_id === meId
                    ? "You"
                    : (message.reply_to.sender_name ?? "Unknown")}
                </span>
                <span
                  className={`block truncate text-[13px] ${
                    outgoing ? "text-white/75" : "text-sig-text-2"
                  }`}
                >
                  {message.reply_to.preview}
                </span>
              </span>
            </button>
          )}

          {voiceNote && <VoiceMessage attachment={voiceNote} outgoing={outgoing} />}

          {previewUrl && <LinkPreviewCard url={previewUrl} outgoing={outgoing} />}

          {!deleted && !voiceNote && message.attachments.length > 0 && (
            <MessageAttachments
              attachments={message.attachments}
              outgoing={outgoing}
              onOpenImage={onOpenImage}
            />
          )}

          {(deleted || message.content) && (
            <p
              className={`whitespace-pre-wrap break-words text-[14.5px] leading-[1.4] ${
                deleted ? "italic opacity-70" : ""
              }`}
            >
              {deleted ? (
                "This message was deleted"
              ) : (
                <LinkifiedText text={message.content ?? ""} outgoing={outgoing} />
              )}
              {/* Reserve space so the timestamp never overlaps the last word. */}
              <span className="pointer-events-none inline-block w-[62px] select-none" />
            </p>
          )}

          {/* An attachment-only bubble still needs room for the timestamp. */}
          {!deleted && !message.content && message.attachments.length > 0 && (
            <span className="block h-[15px]" />
          )}

          {/* WhatsApp's hover chevron. It fades into the bubble so it never
              sits on bare text, and it is the only entry point to the menu. */}
          {!deleted && (
            <button
              ref={chevron}
              onClick={(event) => {
                event.stopPropagation();
                if (menuOpen) setMenuOpen(false);
                else openMenu();
              }}
              aria-label="Message options"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              className={`absolute right-0 top-0 flex h-[26px] w-9 items-center justify-end rounded-tr-[18px] pr-1.5 transition-opacity ${
                outgoing ? "text-white/85" : "text-sig-text-2"
              } ${
                menuOpen
                  ? "opacity-100"
                  : "opacity-0 focus-visible:opacity-100 group-hover/message:opacity-100"
              }`}
              style={{
                background: `linear-gradient(to left, ${
                  outgoing ? "var(--sig-bubble-out)" : "var(--sig-bubble-in)"
                } 60%, transparent)`,
              }}
            >
              <ChevronDownIcon size={16} strokeWidth={2.4} />
            </button>
          )}

          {menuOpen &&
            menuAnchor &&
            createPortal(
              <div
                ref={menuBox}
                style={{
                  position: "fixed",
                  left: menuAnchor.left,
                  top: menuAnchor.top,
                  transform: `${menuAnchor.flipX ? "translateX(-100%)" : ""} ${menuAnchor.flipY ? "translateY(-100%)" : ""}`,
                  zIndex: 60,
                }}
              >
                <div
                  role="menu"
                  className="animate-pop w-44 overflow-hidden rounded-lg border py-1 text-sig-text"
                  style={{
                    background: "var(--sig-elevated)",
                    borderColor: "var(--sig-border)",
                    boxShadow: "var(--sig-shadow)",
                  }}
                >
          <MenuItem icon={<EmojiIcon size={15} />} label="React" onClick={openPicker} />
          <MenuItem
            icon={<ReplyIcon size={15} />}
            label="Reply"
            onClick={() => {
              onReply(message);
              setMenuOpen(false);
            }}
          />
          <MenuItem
            icon={<ForwardIcon size={15} />}
            label="Forward"
            onClick={() => {
              onForward(message);
              setMenuOpen(false);
            }}
          />
          {(message.content ?? "").trim() !== "" && (
            <MenuItem
              icon={<CopyIcon size={15} />}
              label="Copy text"
              onClick={() => {
                onCopy(message.content ?? "");
                setMenuOpen(false);
              }}
            />
          )}
          {outgoing && (
            <MenuItem
              icon={<TrashIcon size={15} />}
              label="Delete"
              danger
              onClick={() => {
                onDelete(message);
                setMenuOpen(false);
              }}
            />
          )}
                </div>
              </div>,
              document.body,
            )}

          <span
            className={`absolute bottom-[6px] right-3 flex select-none items-center gap-1 text-[11px] ${
              outgoing ? "text-white/70" : "text-sig-text-3"
            }`}
          >
            {message.edited_at && !deleted && <span className="italic">edited</span>}
            {message.expires_at && !deleted && (
              <TimerIcon
                size={11}
                strokeWidth={2.2}
                className={outgoing ? "text-white/70" : "text-sig-text-3"}
              />
            )}
            <span>{timeOfDay(message.created_at)}</span>
            {outgoing && !deleted && (
              <StatusTick
                status={message.status}
                // Signal draws ticks in the bubble's contrast colour; a literal
                // blue tick would vanish on a blue bubble, so "read" gets a
                // light blue that stays legible and unmistakably different from
                // the muted white of sent/delivered.
                className={
                  message.status === "read" ? "text-[#B9D3FF]" : "text-white/65"
                }
              />
            )}
          </span>
        </div>

        {Object.keys(grouped).length > 0 && (
          <div
            className={`-mt-2 flex gap-1 rounded-full border px-1.5 py-0.5 ${
              outgoing ? "mr-2" : "ml-2"
            }`}
            style={{
              background: "var(--sig-elevated)",
              borderColor: "var(--sig-border)",
            }}
          >
            {Object.entries(grouped).map(([emoji, userIds]) => (
              <button
                key={emoji}
                onClick={() => onReact(message, emoji)}
                title={userIds.includes(meId) ? "Remove your reaction" : "React"}
                className={`flex items-center gap-0.5 rounded-full px-1 text-[13px] transition-transform hover:scale-110 ${
                  userIds.includes(meId) ? "text-ultramarine-light" : ""
                }`}
              >
                <span>{emoji}</span>
                {userIds.length > 1 && (
                  <span className="text-[11px] text-sig-text-2">{userIds.length}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {reactionsOpen &&
        pickerAnchor &&
        createPortal(
          <div
            ref={pickerBox}
            style={{
              position: "fixed",
              left: pickerAnchor.left,
              top: pickerAnchor.top,
              transform: `${pickerAnchor.flipX ? "translateX(-100%)" : ""} ${pickerAnchor.flipY ? "translateY(-100%)" : ""}`,
              zIndex: 60,
            }}
          >
            <div className="animate-pop" role="menu" aria-label="React to message">
          <div
            className={`flex gap-1 rounded-full border px-2 py-1.5 ${
              pickerExpanded ? "rounded-b-none" : ""
            }`}
            style={{
              background: "var(--sig-elevated)",
              borderColor: "var(--sig-border)",
              boxShadow: "var(--sig-shadow)",
            }}
          >
            {QUICK_REACTIONS.map((emoji) => {
              const mine = grouped[emoji]?.includes(meId);
              return (
                <button
                  key={emoji}
                  onClick={() => react(emoji)}
                  aria-pressed={mine}
                  title={mine ? "Remove your reaction" : `React ${emoji}`}
                  className={`rounded-full px-1 text-[18px] transition-transform hover:scale-125 ${
                    mine ? "bg-sig-active scale-110" : ""
                  }`}
                >
                  {emoji}
                </button>
              );
            })}
            <button
              onClick={() => setPickerExpanded((open) => !open)}
              aria-expanded={pickerExpanded}
              title={pickerExpanded ? "Fewer emoji" : "More emoji"}
              className="ml-0.5 flex h-6 w-6 items-center justify-center self-center rounded-full text-[15px] leading-none text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text"
              style={{ background: "var(--sig-hover)" }}
            >
              {pickerExpanded ? "−" : "+"}
            </button>
          </div>

          {pickerExpanded && (
            <div
              className="grid w-[248px] grid-cols-8 gap-0.5 rounded-b-2xl border border-t-0 p-2"
              style={{
                background: "var(--sig-elevated)",
                borderColor: "var(--sig-border)",
                boxShadow: "var(--sig-shadow)",
              }}
            >
              {MORE_REACTIONS.map((emoji) => (
                <button
                  key={emoji}
                  onClick={() => react(emoji)}
                  title={`React ${emoji}`}
                  className="rounded-md py-0.5 text-[17px] transition-transform hover:scale-125"
                >
                  {emoji}
                </button>
              ))}
            </div>
          )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}


function MenuItem({
  icon,
  label,
  onClick,
  danger = false,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center gap-2.5 px-3 py-2 text-left text-[14px] transition-colors hover:bg-sig-hover ${
        danger ? "text-sig-danger" : "text-sig-text"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}

export const MessageBubble = memo(MessageBubbleBase);
