import {
  createContext,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { mockRooms, mockNotifications } from "../data/mockData";
import type { Room, User, Notification } from "../types";

interface AppContextValue {
  rooms: Room[];
  user: User | null;
  setUser: React.Dispatch<React.SetStateAction<User | null>>;
  darkMode: boolean;
  setDarkMode: React.Dispatch<React.SetStateAction<boolean>>;
  wishlist: number[];
  toggleWishlist: (roomId: number) => void;
  notifications: Notification[];
  setNotifications: React.Dispatch<React.SetStateAction<Notification[]>>;
  markAllRead: () => void;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

interface AppProviderProps {
  children: ReactNode;
}

export function AppProvider({ children }: AppProviderProps) {
  const [rooms] = useState<Room[]>(mockRooms);
  const [user, setUser] = useState<User | null>(null);
  const [darkMode, setDarkMode] = useState<boolean>(false);
  const [wishlist, setWishlist] = useState<number[]>([]);
  const [notifications, setNotifications] =
    useState<Notification[]>(mockNotifications);

  const toggleWishlist = (roomId: number) => {
    setWishlist((prev) =>
      prev.includes(roomId)
        ? prev.filter((id) => id !== roomId)
        : [...prev, roomId]
    );
  };

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  return (
    <AppContext.Provider
      value={{
        rooms,
        user,
        setUser,
        darkMode,
        setDarkMode,
        wishlist,
        toggleWishlist,
        notifications,
        setNotifications,
        markAllRead,
      }}
    >
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
