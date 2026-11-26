"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Shown instead of the app after a self-service sign-up, until the emailed link is opened. */
export function VerifyEmailGate({ email, recheck }: { email: string; recheck: () => Promise<unknown> }) {
  const { t } = useI18n();
  const v = t.verifyEmail;
  const [note, setNote] = useState<{ text: string; tone: "ok" | "warn" } | null>(null);
  const [busy, setBusy] = useState<"resend" | "check" | null>(null);

  const resend = async () => {
    setBusy("resend");
    try {
      await api.post("/api/auth/verify-email/resend");
      setNote({ text: v.resent, tone: "ok" });
    } catch (err) {
      setNote({ text: err instanceof ApiError && err.status === 429 ? t.login.rateLimited : t.common.error, tone: "warn" });
    } finally {
      setBusy(null);
    }
  };
  const check = async () => {
    setBusy("check");
    const me = (await recheck()) as { email_verification_required?: boolean } | undefined;
    if (me?.email_verification_required) setNote({ text: v.notYet, tone: "warn" });
    setBusy(null);
  };

  return (
    <AuthShell title={v.title}>
      <Panel className="space-y-5 p-5 sm:p-7">
        <p className="text-sm text-ink">
          {v.sentTo} <bdi dir="ltr" className="font-semibold">{email}</bdi>. {v.activate}
        </p>
        <p className="text-sm text-ink-2">{v.spam}</p>
        {note && <p role="status" className={note.tone === "ok" ? "text-sm text-ink" : "text-sm text-danger"}>{note.text}</p>}
        <div className="flex flex-col gap-3 sm:flex-row">
          <Button variant="primary" size="lg" className="flex-1" loading={busy === "check"} onClick={check}>{v.confirmed}</Button>
          <Button size="lg" className="flex-1" loading={busy === "resend"} onClick={resend}>{v.resend}</Button>
        </div>
      </Panel>
      <p className="text-center text-sm text-ink-2">
        <button type="button" className="font-semibold text-ink underline-offset-4 hover:underline"
          onClick={async () => { await api.post("/api/auth/logout").catch(() => undefined); window.location.assign("/login"); }}>
          {t.common.logout}
        </button>
      </p>
    </AuthShell>
  );
}

/** The page the emailed link opens. Works signed out, so the link can be opened on another device. */
export function VerifyEmailLanding() {
  const { t } = useI18n();
  const v = t.verifyEmail;
  const token = useSearchParams().get("token") ?? "";
  const [state, setState] = useState<"checking" | "done" | "invalid">(token ? "checking" : "invalid");
  const sent = useRef(false);

  useEffect(() => {
    if (!token || sent.current) return;  // a link works once: never post it twice (React strict mode runs effects twice)
    sent.current = true;
    api.post("/api/auth/verify-email", { token }).then(() => setState("done"), () => setState("invalid"));
  }, [token]);

  return (
    <AuthShell title={v.title}>
      <Panel className="space-y-5 p-5 sm:p-7">
        {state === "checking" && <p role="status" className="text-sm text-ink-2">{v.checking}</p>}
        {state === "done" && <>
          <p role="status" className="text-sm text-ink">{v.done}</p>
          <Link href="/"><Button variant="primary" size="lg" className="w-full">{v.open}</Button></Link>
        </>}
        {state === "invalid" && <>
          <p role="alert" className="text-sm text-danger">{v.invalid}</p>
          <Link href="/login"><Button size="lg" className="w-full">{t.recover.backToLogin}</Button></Link>
        </>}
      </Panel>
    </AuthShell>
  );
}
