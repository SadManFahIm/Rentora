import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { authService } from "../services/authService";
import { useApp } from "../context/AppContext";
import { useWishlistStore } from "../stores/wishlistStore";
import { useNotificationStore } from "../stores/notificationStore";
import type { LoginCredentials, LoginResult, RegisterPayload, User } from "../types";
import { isOtpPending } from "../types";

// ============================================================
// AUTH HOOKS — real dj-rest-auth endpoints, bridged to context
// and the wishlist/notification stores.
// ============================================================

/** Pull the freshly-authenticated user's server-side data into the stores. */
export async function syncUserData(): Promise<void> {
  await Promise.all([
    useWishlistStore.getState().syncFromServer(),
    useNotificationStore.getState().fetch(),
  ]);
}

/** The current authenticated user (from context). */
export function useUser(): { user: User | null; isAuthenticated: boolean } {
  const { user } = useApp();
  return { user, isAuthenticated: user != null };
}

/** Complete an authentication: store the user, hydrate stores, invalidate queries. */
async function completeAuth(
  user: User,
  queryClient: ReturnType<typeof useQueryClient>,
  setUser: (u: User) => void
) {
  setUser(user);
  await syncUserData();
  queryClient.invalidateQueries();
}

export function useLogin() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: LoginCredentials) => authService.login(credentials),
    onSuccess: async (result: LoginResult) => {
      // 2FA accounts get a pending OTP challenge — nothing is stored yet;
      // the Auth page drives the code step and calls useVerifyOtp().
      if (isOtpPending(result)) return;
      await completeAuth(result.user, queryClient, setUser);
    },
  });
}

/** Verify the emailed one-time code and finish the 2FA login. */
export function useVerifyOtp() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ challenge, code }: { challenge: string; code: string }) =>
      authService.verifyOtp(challenge, code),
    onSuccess: async (user) => {
      await completeAuth(user, queryClient, setUser);
    },
  });
}

export function useRegister() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RegisterPayload) => authService.register(payload),
    onSuccess: async (user) => {
      setUser(user);
      await syncUserData();
      queryClient.invalidateQueries();
    },
  });
}

export function useLogout() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: () => authService.logout(),
    onSuccess: () => {
      setUser(null);
      useWishlistStore.getState().clearWishlist();
      useNotificationStore.getState().clear();
      queryClient.clear();
      navigate("/auth");
    },
  });
}
