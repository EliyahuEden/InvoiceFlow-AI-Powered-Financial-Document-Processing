"use client";

import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Field, Input, Panel, PanelHeader } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Status = { enabled: boolean; enabled_at: string | null; recovery_codes_left: number };
type Setup = { secret: string; otpauth_uri: string; qr: string };
type Mode = "idle" | "setup" | "codes" | "off" | "renew";

/** Your own two-factor sign-in: set up with an authenticator app, recovery codes, turn off. */
export function TwoFactorPanel() {
  const { t, locale } = useI18n();
  const m = t.twoFactor;
  const { data, mutate } = useApi<Status>("/api/auth/2fa");
  const [mode, setMode] = useState<Mode>("idle");
  const [setup, setSetup] = useState<Setup | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = () => { setMode("idle"); setSetup(null); setCode(""); setPassword(""); setError(null); };
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try { await fn(); } catch (e) {
      setError(e instanceof ApiError && (e.status === 403 || e.status === 422) ? m.wrong : e instanceof ApiError ? e.message : t.common.error);
    } finally { setBusy(false); }
  };
  const start = () => run(async () => { setSetup(await api.post<Setup>("/api/auth/2fa/setup")); setMode("setup"); });
  const enable = () => run(async () => {
    const r = await api.post<{ recovery_codes: string[] }>("/api/auth/2fa/enable", { code });
    setCodes(r.recovery_codes); setCode(""); setSetup(null); setMode("codes"); mutate(); toast.success(m.enabled);
  });
  const disable = () => run(async () => {
    const value = code.trim();
    const isCode = /^\d{6}$/.test(value.replace(/\s/g, ""));
    await api.post("/api/auth/2fa/disable", { password, ...(isCode ? { code: value } : { recovery_code: value }) });
    reset(); mutate(); toast.success(m.disabled);
  });
  const renew = () => run(async () => {
    const r = await api.post<{ recovery_codes: string[] }>("/api/auth/2fa/recovery-codes", { code });
    setCodes(r.recovery_codes); setCode(""); setMode("codes"); mutate();
  });
  const copy = async () => {
    try { await navigator.clipboard.writeText(codes.join("\n")); toast.success(m.copied); } catch { toast.error(t.common.error); }
  };

  const codeInput = (id: string, labelText: string, recovery = false) => (
    <Field label={labelText} htmlFor={id}>
      <Input id={id} dir="ltr" autoComplete="one-time-code" inputMode={recovery ? "text" : "numeric"} maxLength={recovery ? 20 : 6}
        className="font-mono tracking-widest" value={code} onChange={(e) => setCode(e.target.value)} />
    </Field>
  );

  return (
    <Panel>
      <PanelHeader title={m.title} sub={m.sub}
        actions={data && <span className={data.enabled ? "inline-flex items-center gap-1.5 text-sm font-medium text-ok" : "text-sm text-ink-3"}>
          {data.enabled && <ShieldCheck className="h-4 w-4" aria-hidden />}{data.enabled ? m.on : m.off}</span>} />
      <div className="space-y-4 p-4">
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}

        {mode === "idle" && data && !data.enabled && <Button variant="primary" loading={busy} onClick={start}>{m.start}</Button>}

        {mode === "idle" && data?.enabled && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <p className="text-sm text-ink-2">
              {data.enabled_at && <>{m.since} {date(data.enabled_at, locale)} · </>}
              <span className="num">{data.recovery_codes_left}</span> {m.left}
            </p>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => setMode("renew")}>{m.newCodes}</Button>
              <Button size="sm" variant="danger" onClick={() => setMode("off")}>{m.turnOff}</Button>
            </div>
          </div>
        )}

        {mode === "setup" && setup && (
          <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); enable(); }}>
            <p className="text-sm text-ink-2">{m.scan}</p>
            <div className="flex flex-wrap items-start gap-4">
              {/* the SVG is rendered as an image, never injected into the page; a data URI, so next/image adds nothing */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={setup.qr.startsWith("data:image/svg+xml") ? setup.qr : ""} alt={m.qrAlt}
                width={180} height={180} className="rounded-lg border border-line bg-white p-1" />
              <div className="min-w-0 space-y-1">
                <p className="text-xs text-ink-3">{m.key}</p>
                <code className="ltr block break-all rounded-md bg-sunken px-2 py-1.5 font-mono text-sm">{setup.secret.match(/.{1,4}/g)?.join(" ")}</code>
              </div>
            </div>
            <div className="max-w-[220px]">{codeInput("tf-enable", m.code)}</div>
            <div className="flex gap-2">
              <Button type="submit" variant="primary" loading={busy} disabled={code.length !== 6}>{m.confirm}</Button>
              <Button type="button" variant="ghost" onClick={reset}>{m.cancel}</Button>
            </div>
          </form>
        )}

        {mode === "codes" && (
          <div className="space-y-3">
            <p className="text-sm text-ink">{m.saveCodes}</p>
            <ul className="ltr grid max-w-[360px] grid-cols-2 gap-x-6 gap-y-1 rounded-lg bg-sunken p-3 font-mono text-sm">
              {codes.map((c) => <li key={c}>{c}</li>)}
            </ul>
            <div className="flex gap-2">
              <Button onClick={copy}>{m.copy}</Button>
              <Button variant="primary" onClick={() => { setCodes([]); reset(); }}>{m.done}</Button>
            </div>
          </div>
        )}

        {mode === "off" && (
          <form className="max-w-md space-y-4" onSubmit={(e) => { e.preventDefault(); disable(); }}>
            <p className="text-sm text-ink-2">{m.turnOffHint}</p>
            <Field label={m.password} htmlFor="tf-password">
              <Input id="tf-password" type="password" dir="ltr" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
            </Field>
            {codeInput("tf-off", m.codeOrRecovery, true)}
            <div className="flex gap-2">
              <Button type="submit" variant="danger" loading={busy} disabled={!password || !code}>{m.turnOff}</Button>
              <Button type="button" variant="ghost" onClick={reset}>{m.cancel}</Button>
            </div>
          </form>
        )}

        {mode === "renew" && (
          <form className="max-w-md space-y-4" onSubmit={(e) => { e.preventDefault(); renew(); }}>
            <p className="text-sm text-ink-2">{m.newCodesHint}</p>
            <div className="max-w-[220px]">{codeInput("tf-renew", m.code)}</div>
            <div className="flex gap-2">
              <Button type="submit" variant="primary" loading={busy} disabled={code.length !== 6}>{m.newCodes}</Button>
              <Button type="button" variant="ghost" onClick={reset}>{m.cancel}</Button>
            </div>
          </form>
        )}
      </div>
    </Panel>
  );
}
