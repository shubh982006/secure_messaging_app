"use client";

import { useStore } from "@/lib/store";
import { LockIcon, SignalLogo } from "@/components/icons";

/** Signal's empty state when no conversation is selected. */
export default function ChatsIndexPage() {
  const count = useStore((state) => state.conversations.length);

  return (
    <section className="sig-canvas hidden h-full flex-1 flex-col items-center justify-center px-8 text-center md:flex">
      <SignalLogo size={72} className="text-sig-border" />
      <h2 className="mt-6 text-[20px] font-semibold text-sig-text">Signal</h2>
      <p className="mt-2 max-w-[340px] text-[14px] leading-relaxed text-sig-text-2">
        {count > 0
          ? "Select a chat to start messaging."
          : "Start a new chat to begin messaging."}
      </p>
      <p className="mt-8 flex items-center gap-1.5 text-[12.5px] text-sig-text-3">
        <LockIcon size={13} />
        Your messages are private.
      </p>
    </section>
  );
}
