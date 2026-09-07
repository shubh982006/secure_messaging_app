/**
 * Signal's icon set, hand drawn as inline SVG.
 *
 * Traced to match Signal Desktop's glyphs (24px grid, 2px strokes, round caps)
 * rather than pulling a generic icon package - the icon shapes are a large part
 * of why the app reads as Signal.
 */

type IconProps = {
  className?: string;
  size?: number;
  strokeWidth?: number;
};

function svgProps({ size = 20, className, strokeWidth = 1.8 }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    className,
    "aria-hidden": true,
  };
}

/** The Signal wordmark's speech-bubble glyph. */
export function SignalLogo({ size = 32, className }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="currentColor"
      className={className}
      aria-hidden
    >
      <path d="M12 2C6.201 2 1.5 6.03 1.5 11c0 2.53 1.221 4.816 3.185 6.45a.6.6 0 0 1 .2.57l-.63 3.2a.6.6 0 0 0 .83.66l3.53-1.57a.6.6 0 0 1 .41-.03c.94.24 1.93.37 2.975.37 5.799 0 10.5-4.03 10.5-9S17.799 2 12 2Z" />
    </svg>
  );
}

export function ChatsIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5Z" />
    </svg>
  );
}

export function CallIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.79 19.79 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.1 9.9a16 16 0 0 0 6 6l1.26-1.26a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92Z" />
    </svg>
  );
}

export function VideoIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="m23 7-7 5 7 5V7Z" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  );
}

export function StoriesIcon(props: IconProps) {
  // A segmented story ring around a filled dot - deliberately distinct from the
  // settings gear that sits a few pixels away in the rail.
  return (
    <svg {...svgProps(props)}>
      <path d="M12 3a9 9 0 0 1 6.36 2.64" />
      <path d="M21 12a9 9 0 0 1-2.64 6.36" />
      <path d="M12 21a9 9 0 0 1-6.36-2.64" />
      <path d="M3 12a9 9 0 0 1 2.64-6.36" />
      <circle cx="12" cy="12" r="3.6" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

export function ComposeIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function BackIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  );
}

export function KebabIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <circle cx="12" cy="5" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <circle cx="12" cy="19" r="1.4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function EmojiIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 14.5a4.2 4.2 0 0 0 7 0" />
      <circle cx="9" cy="10" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="15" cy="10" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function MicIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M19 10.5a7 7 0 0 1-14 0M12 17.5V21M8.5 21h7" />
    </svg>
  );
}

export function SendIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M4 12h15M12.5 5.5 19 12l-6.5 6.5" />
    </svg>
  );
}

export function AttachIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M21.44 11.05 12.25 20.24a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.67 3.67 0 1 1 5.19 5.19l-9.2 9.19a1.83 1.83 0 1 1-2.59-2.59l8.49-8.48" />
    </svg>
  );
}

export function ReplyIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M9 14 4 9l5-5" />
      <path d="M4 9h9a7 7 0 0 1 7 7v4" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    </svg>
  );
}

export function CopyIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function MuteIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      <path d="M18.63 13A17.9 17.9 0 0 1 18 8M6.26 6.26A5.86 5.86 0 0 0 6 8c0 7-3 9-3 9h14M18 8a6 6 0 0 0-9.33-5" />
      <path d="m2 2 20 20" />
    </svg>
  );
}

export function BellIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

export function GroupIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

export function UserIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

export function DevicesIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <rect x="2" y="4" width="14" height="11" rx="2" />
      <path d="M2 19h11" />
      <rect x="17" y="9" width="5" height="11" rx="1.5" />
    </svg>
  );
}

export function PaletteIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M12 21a9 9 0 1 1 9-9c0 1.66-1.34 3-3 3h-1.5a2.5 2.5 0 0 0-1.77 4.27A1.5 1.5 0 0 1 12 21Z" />
      <circle cx="7.5" cy="12" r="1" fill="currentColor" stroke="none" />
      <circle cx="9.5" cy="8" r="1" fill="currentColor" stroke="none" />
      <circle cx="14.5" cy="8" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function LeaveIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5M21 12H9" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="m4 12 5 5L20 6" />
    </svg>
  );
}

/**
 * Delivery ticks.
 *
 * sending   - a clock, matching Signal's pending state
 * sent      - one check
 * delivered - two checks
 * read      - two checks, tinted (Signal's own read state on the blue bubble)
 */
export function StatusTick({
  status,
  className,
}: {
  status: "sending" | "sent" | "delivered" | "read" | "failed";
  className?: string;
}) {
  if (status === "sending") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" className={className} aria-label="Sending">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5V12l3 1.8" />
      </svg>
    );
  }
  if (status === "failed") {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
        strokeWidth="2" strokeLinecap="round" className={className} aria-label="Failed to send">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7.5v5M12 16.2v.2" />
      </svg>
    );
  }
  if (status === "sent") {
    return (
      <svg width="16" height="12" viewBox="0 0 18 12" fill="none" stroke="currentColor"
        strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
        className={className} aria-label="Sent">
        <path d="M2 6.5 5.5 10 13 2.5" />
      </svg>
    );
  }
  return (
    <svg width="16" height="12" viewBox="0 0 18 12" fill="none" stroke="currentColor"
      strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"
      className={className} aria-label={status === "read" ? "Read" : "Delivered"}>
      <path d="M1 6.5 4.5 10 11.5 2.5" />
      <path d="M7.5 8.6 8.8 10l7-7.5" />
    </svg>
  );
}


export function TimerIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <circle cx="12" cy="13" r="8" />
      <path d="M12 9.5V13l2.4 1.4M9 2h6" />
    </svg>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M12 3v12M7.5 10.5 12 15l4.5-4.5" />
      <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </svg>
  );
}

export function FileIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v5h5" />
    </svg>
  );
}

export function ImageIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <circle cx="8.5" cy="9.5" r="1.5" />
      <path d="m21 15-5-5L7 19" />
    </svg>
  );
}

export function KeyboardIcon(props: IconProps) {
  return (
    <svg {...svgProps(props)}>
      <rect x="2" y="6" width="20" height="12" rx="2" />
      <path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M8 14h8" />
    </svg>
  );
}
