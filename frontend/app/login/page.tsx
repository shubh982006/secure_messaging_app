"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, api, tokens } from "@/lib/api";
import { Avatar } from "@/components/Avatar";
import { PrimaryButton } from "@/components/Modal";
import { LockIcon, SignalLogo } from "@/components/icons";

type Step = "phone" | "code" | "profile";

const COUNTRIES = [
  { code: "+91", flag: "IN" },
  { code: "+1", flag: "US" },
  { code: "+44", flag: "GB" },
  { code: "+61", flag: "AU" },
  { code: "+49", flag: "DE" },
  { code: "+65", flag: "SG" },
];

const DEMO_ACCOUNTS = [
  { name: "Alice Chen", phone: "+919999900001" },
  { name: "Bob Martinez", phone: "+919999900002" },
  { name: "Carol Nair", phone: "+919999900003" },
  { name: "Dave Okafor", phone: "+919999900004" },
  { name: "Erin Walsh", phone: "+919999900005" },
];

export default function LoginPage() {
  const router = useRouter();

  const [step, setStep] = useState<Step>("phone");
  const [dialCode, setDialCode] = useState("+91");
  const [national, setNational] = useState("");
  const [digits, setDigits] = useState<string[]>(Array(6).fill(""));
  const [mockedCode, setMockedCode] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [about, setAbout] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const codeInputs = useRef<(HTMLInputElement | null)[]>([]);
  const phoneNumber = `${dialCode}${national.replace(/\D/g, "")}`;

  useEffect(() => {
    if (tokens.access) router.replace("/chats");
  }, [router]);

  useEffect(() => {
    if (step === "code") codeInputs.current[0]?.focus();
  }, [step]);

  async function requestCode() {
    if (phoneNumber.replace(/\D/g, "").length < 8) {
      setError("Enter a valid phone number");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await api.requestOtp(phoneNumber);
      setMockedCode(response.mocked_code);
      setDigits(response.mocked_code.split(""));
      setStep("code");
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Could not send the code");
    } finally {
      setBusy(false);
    }
  }

  async function verify(code: string) {
    setBusy(true);
    setError(null);
    try {
      const response = await api.verifyOtp(phoneNumber, code);
      tokens.set(response.access_token, response.refresh_token);
      if (response.is_new_user || !response.user.display_name) {
        setStep("profile");
      } else {
        router.replace("/chats");
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Verification failed");
      setDigits(Array(6).fill(""));
      codeInputs.current[0]?.focus();
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile() {
    if (!displayName.trim()) {
      setError("Your name is required");
      return;
    }
    setBusy(true);
    try {
      await api.updateProfile({
        display_name: displayName.trim(),
        about: about.trim() || "On Signal",
      });
      router.replace("/chats");
    } catch {
      setError("Could not save your profile");
      setBusy(false);
    }
  }

  function onDigitChange(index: number, value: string) {
    const cleaned = value.replace(/\D/g, "");
    const next = [...digits];
    if (!cleaned) {
      next[index] = "";
      setDigits(next);
      return;
    }
    // Support pasting the whole code into any box.
    cleaned.split("").forEach((char, offset) => {
      if (index + offset < 6) next[index + offset] = char;
    });
    setDigits(next);
    codeInputs.current[Math.min(index + cleaned.length, 5)]?.focus();
    if (next.every(Boolean)) void verify(next.join(""));
  }

  async function loginAs(phone: string) {
    setBusy(true);
    setError(null);
    try {
      await api.requestOtp(phone);
      const response = await api.verifyOtp(phone, "123456");
      tokens.set(response.access_token, response.refresh_token);
      router.replace("/chats");
    } catch {
      setError("Could not sign in — is the backend running?");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh flex-col items-center justify-center bg-sig-bg px-5 py-10">
      <div className="w-full max-w-[400px]">
        <div className="mb-9 flex flex-col items-center text-center">
          <div className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-ultramarine">
            <SignalLogo size={34} className="text-white" />
          </div>
          <h1 className="text-[26px] font-semibold tracking-tight text-sig-text">
            {step === "phone" && "Enter your phone number"}
            {step === "code" && "Enter the code we sent"}
            {step === "profile" && "Set up your profile"}
          </h1>
          <p className="mt-2.5 max-w-[330px] text-[14px] leading-relaxed text-sig-text-2">
            {step === "phone" &&
              "Signal will send you a verification code. Carrier rates may apply."}
            {step === "code" && `We sent a 6-digit code to ${phoneNumber}.`}
            {step === "profile" &&
              "Your name and photo are visible to people you message."}
          </p>
        </div>

        {step === "phone" && (
          <form
            onSubmit={(event) => {
              event.preventDefault();
              void requestCode();
            }}
            className="space-y-4"
          >
            <div className="flex gap-2.5">
              <select
                value={dialCode}
                onChange={(event) => setDialCode(event.target.value)}
                className="focus-ring w-[104px] rounded-lg border border-sig-border bg-sig-input px-3 py-3 text-[15px] text-sig-text"
                aria-label="Country code"
              >
                {COUNTRIES.map((country) => (
                  <option key={country.code} value={country.code}>
                    {country.flag} {country.code}
                  </option>
                ))}
              </select>
              <input
                value={national}
                onChange={(event) => setNational(event.target.value.replace(/[^\d\s]/g, ""))}
                placeholder="Phone number"
                inputMode="tel"
                autoFocus
                className="focus-ring flex-1 rounded-lg border border-sig-border bg-sig-input px-4 py-3 text-[15px] text-sig-text placeholder:text-sig-text-3"
              />
            </div>

            {error && <p className="text-[13px] text-sig-danger">{error}</p>}

            <PrimaryButton type="submit" full disabled={busy || !national.trim()}>
              {busy ? "Sending…" : "Continue"}
            </PrimaryButton>
          </form>
        )}

        {step === "code" && (
          <div className="space-y-5">
            <div className="flex justify-center gap-2">
              {digits.map((digit, index) => (
                <input
                  key={index}
                  ref={(element) => {
                    codeInputs.current[index] = element;
                  }}
                  value={digit}
                  onChange={(event) => onDigitChange(index, event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Backspace" && !digits[index] && index > 0) {
                      codeInputs.current[index - 1]?.focus();
                    }
                  }}
                  inputMode="numeric"
                  maxLength={6}
                  aria-label={`Digit ${index + 1}`}
                  className="focus-ring h-14 w-12 rounded-lg border border-sig-border bg-sig-input text-center text-[22px] font-medium text-sig-text"
                />
              ))}
            </div>

            {mockedCode && (
              <div className="flex items-center justify-center gap-2 rounded-lg border border-sig-border bg-sig-pane px-3 py-2.5 text-[13px] text-sig-text-2">
                <LockIcon size={14} />
                <span>
                  Verification is mocked — your code is{" "}
                  <strong className="font-semibold text-sig-text">{mockedCode}</strong>
                </span>
              </div>
            )}

            {error && <p className="text-center text-[13px] text-sig-danger">{error}</p>}

            <PrimaryButton
              full
              disabled={busy || digits.some((digit) => !digit)}
              onClick={() => void verify(digits.join(""))}
            >
              {busy ? "Verifying…" : "Verify"}
            </PrimaryButton>

            <div className="flex justify-center gap-6 text-[13px]">
              <button
                onClick={() => setStep("phone")}
                className="text-sig-text-2 transition-colors hover:text-sig-text"
              >
                Change number
              </button>
              <button
                onClick={() => void requestCode()}
                className="text-ultramarine-light transition-opacity hover:opacity-80"
              >
                Resend code
              </button>
            </div>
          </div>
        )}

        {step === "profile" && (
          <div className="space-y-5">
            <div className="flex justify-center">
              <Avatar name={displayName || "?"} seed={phoneNumber} size={88} />
            </div>
            <input
              value={displayName}
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="Your name (required)"
              autoFocus
              maxLength={60}
              className="focus-ring w-full rounded-lg border border-sig-border bg-sig-input px-4 py-3 text-[15px] text-sig-text placeholder:text-sig-text-3"
            />
            <input
              value={about}
              onChange={(event) => setAbout(event.target.value)}
              placeholder="About (optional)"
              maxLength={100}
              className="focus-ring w-full rounded-lg border border-sig-border bg-sig-input px-4 py-3 text-[15px] text-sig-text placeholder:text-sig-text-3"
            />
            {error && <p className="text-[13px] text-sig-danger">{error}</p>}
            <PrimaryButton full disabled={busy} onClick={() => void saveProfile()}>
              {busy ? "Saving…" : "Finish"}
            </PrimaryButton>
          </div>
        )}

        {step === "phone" && (
          <div className="mt-10 border-t border-sig-border pt-6">
            <p className="mb-3 text-center text-[12px] font-medium uppercase tracking-wider text-sig-text-3">
              Demo accounts · code 123456
            </p>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.phone}
                  disabled={busy}
                  onClick={() => void loginAs(account.phone)}
                  className="focus-ring flex items-center gap-2.5 rounded-lg border border-sig-border px-3 py-2.5 text-left transition-colors hover:bg-sig-hover disabled:opacity-50"
                >
                  <Avatar name={account.name} seed={account.phone} size={28} />
                  <span className="truncate text-[13px] text-sig-text">
                    {account.name.split(" ")[0]}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}

        <p className="mt-8 flex items-center justify-center gap-1.5 text-center text-[12px] text-sig-text-3">
          <LockIcon size={12} />
          Messages are private. Stay safe.
        </p>
      </div>
    </main>
  );
}
