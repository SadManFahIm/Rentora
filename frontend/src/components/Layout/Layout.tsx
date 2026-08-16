import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Navbar from "../Navbar/Navbar";
import Footer from "../Footer/Footer";
import CopilotWidget from "../CopilotWidget/CopilotWidget";
import { useUiStore } from "../../stores/uiStore";
import { track } from "../../services/analytics";

export default function Layout() {
  const darkMode = useUiStore((s) => s.darkMode);
  const location = useLocation();
  const isAuthRoute = location.pathname === "/auth";

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  // First-party analytics (Tier 2): one page_view per route change. This is
  // fire-and-forget — a failed POST never affects the page.
  useEffect(() => {
    track("page_view");
  }, [location.pathname]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Navbar />
      <main key={location.pathname} className="animate-in fade-in duration-300">
        <Outlet />
      </main>
      {!isAuthRoute && <Footer />}
      {!isAuthRoute && <CopilotWidget />}
    </div>
  );
}
