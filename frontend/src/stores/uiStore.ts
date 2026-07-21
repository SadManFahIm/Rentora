import { create } from "zustand";
import { persist } from "zustand/middleware";

// ============================================================
// UI STORE — client-only presentation state (no server data)
// ============================================================

interface UiState {
  darkMode: boolean;
  sidebarOpen: boolean;
  toggleDarkMode: () => void;
  setDarkMode: (value: boolean) => void;
  toggleSidebar: () => void;
  setSidebarOpen: (value: boolean) => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      darkMode: false,
      sidebarOpen: false,
      toggleDarkMode: () => set((s) => ({ darkMode: !s.darkMode })),
      setDarkMode: (value) => set({ darkMode: value }),
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setSidebarOpen: (value) => set({ sidebarOpen: value }),
    }),
    {
      name: "rentora-ui",
      // Only persist darkMode — sidebar is ephemeral per session.
      partialize: (state) => ({ darkMode: state.darkMode }),
    }
  )
);
