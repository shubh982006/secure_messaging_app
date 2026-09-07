"use client";

import { useEffect, type ReactNode } from "react";

import { CloseIcon } from "./icons";

interface ModalProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: number;
}

export function Modal({ open, title, onClose, children, footer, width = 420 }: ModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className="animate-pop flex max-h-[86vh] w-full flex-col overflow-hidden rounded-2xl"
        style={{
          maxWidth: width,
          background: "var(--sig-elevated)",
          boxShadow: "var(--sig-shadow)",
        }}
      >
        <header className="flex items-center justify-between px-5 pb-3 pt-5">
          <h2 className="text-[17px] font-semibold text-sig-text">{title}</h2>
          <button
            onClick={onClose}
            className="focus-ring -mr-2 rounded-full p-2 text-sig-text-2 transition-colors hover:bg-sig-hover hover:text-sig-text"
            aria-label="Close"
          >
            <CloseIcon size={18} />
          </button>
        </header>

        <div className="sig-scroll flex-1 overflow-y-auto px-5 pb-2">{children}</div>

        {footer && <footer className="px-5 pb-5 pt-3">{footer}</footer>}
      </div>
    </div>
  );
}

export function PrimaryButton({
  children,
  disabled,
  onClick,
  type = "button",
  full = false,
  tone = "accent",
}: {
  children: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
  full?: boolean;
  tone?: "accent" | "danger" | "ghost";
}) {
  const palette = {
    accent: "bg-ultramarine text-white hover:bg-ultramarine-hover",
    danger: "bg-transparent text-sig-danger hover:bg-sig-hover",
    ghost: "bg-sig-hover text-sig-text hover:bg-sig-active",
  }[tone];

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={`focus-ring rounded-full px-6 py-2.5 text-[15px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${palette} ${
        full ? "w-full" : ""
      }`}
    >
      {children}
    </button>
  );
}
