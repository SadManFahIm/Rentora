import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppProvider } from "./context/AppContext";

// Styles
import "./styles/global.css";
import "./pages/Home/Home.css";
import "./pages/Rooms/Rooms.css";
import "./pages/Map/Map.css";
import "./pages/Dashboard/Dashboard.css";
import "./pages/Auth/Auth.css";

// Layout
import Layout from "./components/Layout/Layout";

// Pages
import Home from "./pages/Home/Home";
import Rooms from "./pages/Rooms/Rooms";
import Map from "./pages/Map/Map";
import Chat from "./pages/Chat/Chat";
import Dashboard from "./pages/Dashboard/Dashboard";
import Auth from "./pages/Auth/Auth";

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Home />} />
            <Route path="/rooms" element={<Rooms />} />
            <Route path="/map" element={<Map />} />
            <Route path="/chat" element={<Chat />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/auth" element={<Auth />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}
