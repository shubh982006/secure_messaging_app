/** Date / time helpers that mirror how Signal labels things. */

const DAY = 24 * 60 * 60 * 1000;

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function daysApart(a: Date, b: Date): number {
  return Math.round((startOfDay(b) - startOfDay(a)) / DAY);
}

/** "14:32" - the timestamp inside a message bubble. */
export function timeOfDay(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "numeric",
    minute: "2-digit",
  });
}

/** Conversation list column: time today, "Yesterday", weekday, then a date. */
export function listTimestamp(iso: string): string {
  const date = new Date(iso);
  const delta = daysApart(date, new Date());
  if (delta === 0) return timeOfDay(iso);
  if (delta === 1) return "Yesterday";
  if (delta < 7) return date.toLocaleDateString([], { weekday: "short" });
  return date.toLocaleDateString([], { month: "numeric", day: "numeric", year: "2-digit" });
}

/** The centred separator between days in a thread. */
export function dayDivider(iso: string): string {
  const date = new Date(iso);
  const delta = daysApart(date, new Date());
  if (delta === 0) return "Today";
  if (delta === 1) return "Yesterday";
  if (delta < 7) return date.toLocaleDateString([], { weekday: "long" });
  return date.toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
    ...(date.getFullYear() === new Date().getFullYear() ? {} : { year: "numeric" }),
  });
}

export function sameDay(a: string, b: string): boolean {
  return daysApart(new Date(a), new Date(b)) === 0;
}

/** Presence line under the conversation title. */
export function presenceLabel(isOnline: boolean, lastSeenAt: string | null): string {
  if (isOnline) return "Online";
  if (!lastSeenAt) return "Offline";

  const date = new Date(lastSeenAt);
  const minutes = Math.floor((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "Last seen just now";
  if (minutes < 60) return `Last seen ${minutes}m ago`;

  const delta = daysApart(date, new Date());
  if (delta === 0) return `Last seen today at ${timeOfDay(lastSeenAt)}`;
  if (delta === 1) return `Last seen yesterday at ${timeOfDay(lastSeenAt)}`;
  return `Last seen ${date.toLocaleDateString([], { month: "short", day: "numeric" })}`;
}

export function initials(name: string | null | undefined): string {
  if (!name) return "#";
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "#";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Signal assigns each contact a stable colour derived from their identity. */
const AVATAR_COLORS = [
  "#4B7BEC", "#8E6FD8", "#C86FC9", "#D96A6A", "#D98C4A",
  "#B5A04B", "#6FA85A", "#4FA8A0", "#5C8FB8", "#8A7F72",
];

export function avatarColor(seed: string | null | undefined): string {
  if (!seed) return AVATAR_COLORS[0];
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return AVATAR_COLORS[hash % AVATAR_COLORS.length];
}

export function formatPhone(phone: string): string {
  const digits = phone.replace(/[^\d+]/g, "");
  if (digits.startsWith("+91") && digits.length === 13) {
    return `${digits.slice(0, 3)} ${digits.slice(3, 8)} ${digits.slice(8)}`;
  }
  if (digits.startsWith("+1") && digits.length === 12) {
    return `${digits.slice(0, 2)} (${digits.slice(2, 5)}) ${digits.slice(5, 8)}-${digits.slice(8)}`;
  }
  return digits;
}
