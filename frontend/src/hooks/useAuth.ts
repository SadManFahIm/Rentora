import { useMutation, useQueryClient } from "@tanstack/react-query";
import { authService } from "../services/authService";
import { useApp } from "../context/AppContext";
import type { LoginCredentials, RegisterPayload, User } from "../types";

// ============================================================
// AUTH HOOKS
// Bridge the auth service to the (temporary) AppContext user state.
// When real API auth lands the context can be swapped for a query.
// ============================================================

/** The current authenticated user (from context for now). */
export function useUser(): { user: User | null; isAuthenticated: boolean } {
  const { user } = useApp();
  return { user, isAuthenticated: user != null };
}

export function useLogin() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: LoginCredentials) =>
      (await authService.login(credentials)).data,
    onSuccess: (auth) => {
      setUser(auth.user);
      queryClient.invalidateQueries();
    },
  });
}

export function useRegister() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: RegisterPayload) =>
      (await authService.register(payload)).data,
    onSuccess: (auth) => {
      setUser(auth.user);
      queryClient.invalidateQueries();
    },
  });
}

export function useLogout() {
  const { setUser } = useApp();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await authService.logout()).data,
    onSuccess: () => {
      setUser(null);
      queryClient.clear();
    },
  });
}
