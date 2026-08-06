import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { isAuthenticated, clearTokens } from "../services/api";
import { authService } from "../services/authService";
import { useWishlistStore } from "../stores/wishlistStore";
import { useNotificationStore } from "../stores/notificationStore";
import type { User } from "../types";

// ============================================================
// APP CONTEXT — authenticated user + session bootstrap.
// On load, if tokens are present we restore the session by
// fetching the profile and hydrating the wishlist/notification
// stores from the backend.
// ============================================================

interface AppContextValue {
  user: User | null;
  setUser: React.Dispatch<React.SetStateAction<User | null>>;
  /** True while the initial session-restore is in flight. */
  authLoading: boolean;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

interface AppProviderProps {
  children: ReactNode;
}

export function AppProvider({ children }: AppProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(isAuthenticated());

  useEffect(() => {
    let cancelled = false;

    async function restoreSession() {
      if (!isAuthenticated()) {
        setAuthLoading(false);
        return;
      }
      try {
        const profile = await authService.getProfile();
        if (cancelled) return;
        setUser(profile);
        // Hydrate client stores from the server for this session.
        await Promise.all([
          useWishlistStore.getState().syncFromServer(),
          useNotificationStore.getState().fetch(),
        ]);
      } catch {
        // Token invalid/expired and un-refreshable → sign out locally.
        clearTokens();
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setAuthLoading(false);
      }
    }

    restoreSession();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppContext.Provider value={{ user, setUser, authLoading }}>
      {children}
    </AppContext.Provider>
  );
}

// Custom hook
export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useApp must be used within an AppProvider");
  }
  return ctx;
}

export default AppContext;
