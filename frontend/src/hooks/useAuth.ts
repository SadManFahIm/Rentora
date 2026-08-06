import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { authService } from "../services/authService";
import { useApp } from "../context/AppContext";
import { useWishlistStore } from "../stores/wishlistStore";
import { useNotificationStore } from "../stores/notificationStore";
import type { LoginCredentials, RegisterPayload, User } from "../types";

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

export function useLogin() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: LoginCredentials) => authService.login(credentials),
    onSuccess: async (user) => {
      setUser(user);
      await syncUserData();
      queryClient.invalidateQueries();
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
