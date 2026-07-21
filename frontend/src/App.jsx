import { useState, useEffect } from "react";
import { AppProvider, useApp } from "./context/AppContext";

// Styles
import "./styles/global.css";

// Components
import Navbar from "./components/Navbar/Navbar";
import Footer from "./components/Footer/Footer";

// Pages
import Home from "./pages/Home/Home";
import Rooms from "./pages/Rooms/Rooms";
import Map from "./pages/Map/Map";
import Chat from "./pages/Chat/Chat";
import Dashboard from "./pages/Dashboard/Dashboard";
import Auth from "./pages/Auth/Auth";

// Import page-specific CSS
import "./pages/Home/Home.css";
import "./pages/Rooms/Rooms.css";
import "./pages/Map/Map.css";
import "./pages/Dashboard/Dashboard.css";
import "./pages/Auth/Auth.css";

function AppContent() {
  const [page, setPage] = useState("home");
  const { darkMode } = useApp();

  useEffect(() => {
    document.documentElement.className = darkMode ? "dark" : "";
  }, [darkMode]);

  const renderPage = () => {
    switch (page) {
      case "home":      return <Home setPage={setPage} />;
      case "rooms":     return <Rooms />;
      case "map":       return <Map />;
      case "chat":      return <Chat />;
      case "dashboard": return <Dashboard setPage={setPage} />;
      case "auth":      return <Auth setPage={setPage} />;
      default:          return <Home setPage={setPage} />;
    }
  };

  return (
    <div className="app">
      <Navbar page={page} setPage={setPage} />
      <main className="fade-in">{renderPage()}</main>
      {page !== "auth" && <Footer setPage={setPage} />}
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
