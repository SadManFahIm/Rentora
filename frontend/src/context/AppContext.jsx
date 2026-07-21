import { createContext, useContext, useState } from "react";
import { mockRooms, mockNotifications } from "../data/mockData";

const AppContext = createContext();

export function AppProvider({ children }) {
  const [rooms] = useState(mockRooms);
  const [user, setUser] = useState(null);
  const [darkMode, setDarkMode] = useState(false);
  const [wishlist, setWishlist] = useState([]);
  const [notifications, setNotifications] = useState(mockNotifications);

  const toggleWishlist = (roomId) => {
    setWishlist((prev) =>
      prev.includes(roomId) ? prev.filter((id) => id !== roomId) : [...prev, roomId]
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
export function useApp() {
  return useContext(AppContext);
}

export default AppContext;
