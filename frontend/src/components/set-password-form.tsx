"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Input, Panel } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Choose a password from an emailed link: a password reset or a teammate invitation (same endpoint). */
export function SetPasswordForm({ mode }: { mode: "reset" | "invite" }) {
  const { t } = useI18n();
  const r = t.recover;
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [error, setError] = useState<string | null>(null);
  const mismatch = confirm.length > 0 && confirm !== password;
  const ready = !!token && password.length >= 12 && password === confirm;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("busy");
    setError(null);
    try {
      await api.post("/api/auth/reset-password", { token, password });
      setState("done");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t.login.rateLimited : r.invalid);
      setState("idle");
    }
  };

  return (
    <AuthShell title={mode === "invite" ? r.inviteTitle : r.resetTitle}>
      <Panel className="p-5 sm:p-7">
        {state === "done" ? (
          <div className="space-y-5">
            <p role="status" className="text-sm text-ink">{r.done}</p>
            <Link href="/login"><Button variant="primary" size="lg" className="w-full">{r.signIn}</Button></Link>
          </div>
        ) : !token ? (
          <p role="alert" className="text-sm text-danger">{r.missingToken}</p>
        ) : (
          <form onSubmit={submit} className="space-y-5" noValidate>
            <p className="text-sm text-ink-2">{mode === "invite" ? r.inviteSub : r.resetSub}</p>
            <Field label={r.newPassword} htmlFor="new-password" hint={t.signup.passwordHint}>
              <Input id="new-password" type="password" dir="ltr" autoComplete="new-password" required value={password}
                onChange={(e) => setPassword(e.target.value)} maxLength={200} />
            </Field>
            <Field label={r.confirm} htmlFor="confirm-password" hint={mismatch ? r.mismatch : undefined}>
              <Input id="confirm-password" type="password" dir="ltr" autoComplete="new-password" required value={confirm}
                aria-invalid={mismatch} onChange={(e) => setConfirm(e.target.value)} maxLength={200} />
            </Field>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={state === "busy"} disabled={!ready}>
              {r.save}
            </Button>
          </form>
        )}
      </Panel>
      <p className="text-center text-sm text-ink-2"><Link href="/login" className="font-semibold text-ink underline-offset-4 hover:underline">{r.backToLogin}</Link></p>
    </AuthShell>
  );
}
