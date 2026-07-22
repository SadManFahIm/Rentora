import { useNavigate } from "react-router-dom";
import { Badge } from "../ui/badge";

export default function Footer() {
  const navigate = useNavigate();

  return (
    <footer className="border-t border-gray-200 bg-card px-4 pb-6 pt-12 dark:border-gray-800 md:px-6 lg:px-8">
      <div className="mx-auto mb-10 grid max-w-7xl grid-cols-1 gap-10 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="mb-3 flex items-center gap-2 font-display text-xl font-bold text-orange-600">
            🏠 RentRoom <Badge variant="brand">BD</Badge>
          </div>
          <p className="max-w-70 text-sm leading-relaxed text-gray-600 dark:text-gray-400">
            Bangladesh's most trusted AI-powered room rental platform. Find verified, affordable rooms in Dhaka and beyond.
          </p>
        </div>
        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-foreground">Browse</h4>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400" onClick={() => navigate("/rooms")}>
            All Rooms
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400" onClick={() => navigate("/map")}>
            Map View
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400">Featured Listings</a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400">New Listings</a>
        </div>
        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-foreground">Account</h4>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400" onClick={() => navigate("/auth")}>
            Sign In
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400" onClick={() => navigate("/auth")}>
            Register
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400" onClick={() => navigate("/dashboard")}>
            Dashboard
          </a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400" onClick={() => navigate("/chat")}>
            Messages
          </a>
        </div>
        <div>
          <h4 className="mb-4 font-display text-sm font-bold text-foreground">Company</h4>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400">About Us</a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400">Privacy Policy</a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400">Terms of Service</a>
          <a className="mb-2 block cursor-pointer text-sm text-gray-600 hover:text-orange-600 dark:text-gray-400">Contact</a>
        </div>
      </div>
      <div className="mx-auto flex max-w-7xl flex-col items-center gap-2 border-t border-gray-200 pt-5 text-center text-sm text-gray-600 dark:border-gray-800 dark:text-gray-400 sm:flex-row sm:justify-between sm:text-left">
        <span>© 2025 RentRoom BD. All rights reserved.</span>
        <span>Made with ❤️ in Bangladesh</span>
      </div>
    </footer>
  );
}
