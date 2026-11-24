"use client";

import { useState } from "react";
import { useSession } from "@/components/session";
import { Button, Field, Input, Panel, PanelHeader } from "@/components/ui";
import { api, ApiError, useApi } from "@/lib/api";
import { date } from "@/lib/format";
import { useI18n } from "@/lib/i18n";

type Account = { id: string; kind: "iban" | "domestic"; last_four: string; bank_code: string | null;
  branch_code: string | null; proposed_by: string };
type BankState = { confirmed: Account | null; pending: Account | null; hold_until: string | null };

export function SupplierBankPanel({ supplierId }: { supplierId: string }) {
  const { t, locale } = useI18n();
  const m = t.banking;
  const { can, me } = useSession();
  const path = `/api/suppliers/${supplierId}/bank-account`;
  const { data, error, mutate } = useApi<BankState>(path);
  const [editing, setEditing] = useState(false);
  const [foreign, setForeign] = useState(false);
  const [details, setDetails] = useState({ bank_code: "", branch_code: "", account_number: "", iban: "" });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string>();

  const run = async (url: string, body: object) => {
    setBusy(true);
    setProblem(undefined);
    try {
      await mutate(await api.post<BankState>(url, body), false);
      setDetails({ bank_code: "", branch_code: "", account_number: "", iban: "" });
      setEditing(false);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.message : t.common.error);
    } finally {
      setBusy(false);
    }
  };
  const input = (key: keyof typeof details, label: string, length: number) => <Field label={label} htmlFor={`supplier-bank-${key}`}>
    <Input id={`supplier-bank-${key}`} dir="ltr" autoComplete="off" maxLength={length} required value={details[key]}
      inputMode={key === "iban" ? "text" : "numeric"} onChange={(event) => setDetails({ ...details, [key]: event.target.value })} />
  </Field>;
  const masked = (account: Account) => <bdi className="font-mono">{account.kind === "iban" ? "IBAN" : `${account.bank_code} / ${account.branch_code}`} · •••• {account.last_four}</bdi>;

  return <Panel>
    <PanelHeader title={m.title} actions={data && can("masterdata:write") && !data.pending && !editing &&
      <Button onClick={() => setEditing(true)}>{m.propose}</Button>} />
    <div className="space-y-3 p-4">
      {(problem || error) && <p role="alert" className="text-danger">{problem || t.common.error}</p>}
      {data && <p>{m.confirmed} · {data.confirmed ? masked(data.confirmed) : m.none}</p>}
      {data?.hold_until && new Date(data.hold_until).getTime() > Date.now() && <p>{m.hold} {date(data.hold_until, locale)}</p>}
      {data?.pending && <div className="flex flex-wrap items-center gap-3">
        <p>{m.pending} · {masked(data.pending)}</p>
        {can("approval:decide") && data.pending.proposed_by !== me?.user.id && <>
          <Button variant="primary" disabled={busy} onClick={() => run(`${path}/${data.pending?.id}/review`, { decision: "confirm" })}>{m.confirm}</Button>
          <Button disabled={busy} onClick={() => run(`${path}/${data.pending?.id}/review`, { decision: "reject" })}>{m.reject}</Button>
        </>}
      </div>}
      {editing && <form className="space-y-3" onSubmit={(event) => {
        event.preventDefault();
        const { iban, ...domestic } = details;
        void run(path, foreign ? { iban } : domestic);
      }}>
        <label className="flex items-center gap-2"><input type="checkbox" checked={foreign} onChange={(event) => setForeign(event.target.checked)} />{m.foreign}</label>
        {foreign ? input("iban", "IBAN", 48) : <div className="grid gap-3 sm:grid-cols-3">
          {input("bank_code", m.bankCode, 2)}{input("branch_code", m.branchCode, 3)}{input("account_number", m.accountNumber, 20)}
        </div>}
        <div className="flex gap-2">
          <Button variant="primary" type="submit" loading={busy}>{m.submit}</Button>
          <Button type="button" onClick={() => { setEditing(false); setDetails({ bank_code: "", branch_code: "", account_number: "", iban: "" }); }}>{t.common.cancel}</Button>
        </div>
      </form>}
    </div>
  </Panel>;
}
