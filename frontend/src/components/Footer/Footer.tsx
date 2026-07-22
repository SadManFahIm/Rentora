import { useNavigate } from "react-router-dom";
import "./Footer.css";

export default function Footer() {
  const navigate = useNavigate();

  return (
    <footer className="footer">
      <div className="footer-inner">
        <div className="footer-brand">
          <div className="footer-logo">🏠 RentRoom <span>BD</span></div>
          <p>Bangladesh's most trusted AI-powered room rental platform. Find verified, affordable rooms in Dhaka and beyond.</p>
        </div>
        <div className="footer-col">
          <h4>Browse</h4>
          <a onClick={() => navigate("/rooms")}>All Rooms</a>
          <a onClick={() => navigate("/map")}>Map View</a>
          <a>Featured Listings</a>
          <a>New Listings</a>
        </div>
        <div className="footer-col">
          <h4>Account</h4>
          <a onClick={() => navigate("/auth")}>Sign In</a>
          <a onClick={() => navigate("/auth")}>Register</a>
          <a onClick={() => navigate("/dashboard")}>Dashboard</a>
          <a onClick={() => navigate("/chat")}>Messages</a>
        </div>
        <div className="footer-col">
          <h4>Company</h4>
          <a>About Us</a>
          <a>Privacy Policy</a>
          <a>Terms of Service</a>
          <a>Contact</a>
        </div>
      </div>
      <div className="footer-bottom">
        <span>© 2025 RentRoom BD. All rights reserved.</span>
        <span>Made with ❤️ in Bangladesh</span>
      </div>
    </footer>
  );
}
