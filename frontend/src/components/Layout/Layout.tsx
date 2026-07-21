import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Navbar from "../Navbar/Navbar";
import Footer from "../Footer/Footer";
import { useApp } from "../../context/AppContext";

export default function Layout() {
  const { darkMode } = useApp();
  const location = useLocation();
  const isAuthRoute = location.pathname === "/auth";

  useEffect(() => {
    document.documentElement.className = darkMode ? "dark" : "";
  }, [darkMode]);

  return (
    <div className="app">
      <Navbar />
      <main className="fade-in">
        <Outlet />
      </main>
      {!isAuthRoute && <Footer />}
    </div>
  );
}
