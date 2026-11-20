"use client";

import { createContext, useContext } from "react";
import { useApi } from "@/lib/api";

export type Me = {
  user: { id: string; email: string; full_name: string; locale: string };
  organization: { id: string; name: string; slug: string; name_en?: string; base_currency: string };
  role: string;
  permissions: string[];
  organizations: { id: string; name: string; role: string }[];
  ai_mode: string;
};

const SessionContext = createContext<{ me: Me | undefined; can: (perm: string) => boolean }>({
  me: undefined,
  can: () => false,
});

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { data } = useApi<Me>("/api/auth/me");
  const can = (perm: string) => !!data?.permissions.includes(perm);
  return <SessionContext.Provider value={{ me: data, can }}>{children}</SessionContext.Provider>;
}

export function useSession() {
  return useContext(SessionContext);
}
