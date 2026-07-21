import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Navbar from "../Navbar/Navbar";
import Footer from "../Footer/Footer";
import { useUiStore } from "../../stores/uiStore";

export default function Layout() {
  const darkMode = useUiStore((s) => s.darkMode);
  const location = useLocation();
  const isAuthRoute = location.pathname === "/auth";

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
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
