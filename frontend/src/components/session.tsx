"use client";

import { createContext, useContext, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { TwoFactorPanel } from "@/components/two-factor-panel";
import { Button } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export type Me = {
  user: { id: string; email: string; full_name: string; locale: string };
  organization: { id: string; name: string; slug: string; name_en?: string; base_currency: string };
  role: string;
  permissions: string[];
  organizations: { id: string; name: string; role: string }[];
  ai_mode: string;
  mfa_enrollment_required?: boolean;
  two_factor?: boolean;
};

const SessionContext = createContext<{ me: Me | undefined; can: (perm: string) => boolean }>({
  me: undefined,
  can: () => false,
});

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data } = useApi<Me>("/api/auth/me");
  const can = (perm: string) => !!data?.permissions.includes(perm);
  return <SessionContext.Provider value={{ me: data, can }}>
    {data?.mfa_enrollment_required ? <EnrollmentGate /> : children}
  </SessionContext.Provider>;
}

function EnrollmentGate() {
  const { t } = useI18n();
  const path = usePathname();
  const router = useRouter();
  useEffect(() => { if (path !== "/settings") router.replace("/settings"); }, [path, router]);
  return <main className="mx-auto max-w-2xl space-y-4 p-6">
    <h1 className="text-xl font-semibold">{t.twoFactor.enrollmentTitle}</h1>
    <p>{t.twoFactor.enrollmentHint}</p>
    <TwoFactorPanel />
    <Button onClick={async () => { await api.post("/api/auth/logout"); window.location.assign("/login"); }}>{t.common.logout}</Button>
  </main>;
}

export function useSession() {
  return useContext(SessionContext);
}
