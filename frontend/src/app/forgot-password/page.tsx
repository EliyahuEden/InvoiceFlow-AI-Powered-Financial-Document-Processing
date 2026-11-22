"use client";

import Link from "next/link";
import { useState } from "react";
import { AuthShell } from "@/components/auth-shell";
import { Button, Field, Input, Panel } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

/** Ask for a reset link. The confirmation is the same whether or not the address has an account. */
export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const r = t.recover;
  const { data: options } = useApi<{ email_enabled: boolean }>("/api/auth/options");
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "sent">("idle");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("busy");
    setError(null);
    try {
      await api.post("/api/auth/forgot-password", { email });
      setState("sent");
    } catch (err) {
      setError(err instanceof ApiError && err.status === 429 ? t.login.rateLimited : t.common.error);
      setState("idle");
    }
  };

  return (
    <AuthShell title={r.forgotTitle}>
      <Panel className="p-5 sm:p-7">
        {options && !options.email_enabled ? (
          <p role="status" className="text-sm text-ink-2">{r.noEmail}</p>
        ) : state === "sent" ? (
          <p role="status" className="text-sm text-ink">{r.sent}</p>
        ) : (
          <form onSubmit={submit} className="space-y-5" noValidate>
            <p className="text-sm text-ink-2">{r.forgotSub}</p>
            <Field label={t.login.email} htmlFor="email">
              <Input id="email" type="email" dir="ltr" autoComplete="username" required value={email}
                onChange={(e) => setEmail(e.target.value)} maxLength={320} />
            </Field>
            {error && <p role="alert" className="text-sm text-danger">{error}</p>}
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={state === "busy"}
              disabled={!/^[^@\s]+@[^@\s]+$/.test(email)}>{r.send}</Button>
          </form>
        )}
      </Panel>
      <p className="text-center text-sm text-ink-2"><Link href="/login" className="font-semibold text-ink underline-offset-4 hover:underline">{r.backToLogin}</Link></p>
    </AuthShell>
  );
}
