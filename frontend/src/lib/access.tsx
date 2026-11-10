import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getMe, login, officeToken, type Me } from "../api";

interface Access {
  me: Me | null;
  signIn: (password: string) => Promise<void>;
  signOut: () => void;
}

const AccessContext = createContext<Access>({ me: null, signIn: async () => {}, signOut: () => {} });

/** What this visitor may see (public demo, office sign-in), loaded once and after signing in or out. */
export function AccessProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);

  const load = useCallback(() => {
    getMe().then(setMe).catch(() => setMe(null));
  }, []);
  useEffect(load, [load]);

  const signIn = useCallback(async (password: string) => {
    const { token, expires_at } = await login(password);
    officeToken.set(token, expires_at);
    load();
  }, [load]);

  const signOut = useCallback(() => {
    officeToken.clear();
    load();
  }, [load]);

  return <AccessContext.Provider value={{ me, signIn, signOut }}>{children}</AccessContext.Provider>;
}

export const useAccess = () => useContext(AccessContext);
