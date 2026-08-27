import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { AppProvider } from "./context/AppContext";
import { Toaster } from "./components/ui/sonner";
import ErrorBoundary from "./components/ErrorBoundary";
import RouteErrorBoundary from "./components/RouteErrorBoundary";
import PwaBanners from "./components/PwaBanners/PwaBanners";
import { useBackgroundSync } from "./hooks/useBackgroundSync";

// Styles
import "./styles/global.css";

// Layout
import Layout from "./components/Layout/Layout";

// Pages — code-split: each page is fetched only when its route is opened.
const Home = lazy(() => import("./pages/Home/Home"));
const Rooms = lazy(() => import("./pages/Rooms/Rooms"));
const AreaRooms = lazy(() => import("./pages/AreaRooms/AreaRooms"));
const Map = lazy(() => import("./pages/Map/Map"));
const Chat = lazy(() => import("./pages/Chat/Chat"));
const Dashboard = lazy(() => import("./pages/Dashboard/Dashboard"));
const Auth = lazy(() => import("./pages/Auth/Auth"));
const PaymentStatus = lazy(() => import("./pages/PaymentStatus/PaymentStatus"));
const Roommates = lazy(() => import("./pages/Roommates/Roommates"));
const Services = lazy(() => import("./pages/Services/Services"));

/**
 * Suspense boundary around routed content. The shell (nav/footer, query
 * client, auth context) is always present; only the page chunk suspends.
 */
function PageLoader() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <div className="h-8 w-8 animate-spin rounded-full border-2 border-orange-500 border-t-transparent" />
    </div>
  );
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export default function App() {
  useBackgroundSync();

  return (
    <QueryClientProvider client={queryClient}>
      <AppProvider>
        <ErrorBoundary>
          <BrowserRouter>
            <Suspense fallback={<PageLoader />}>
              <Routes>
                <Route element={<Layout />}>
                  <Route
                    path="/"
                    element={
                      <RouteErrorBoundary>
                        <Home />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/rooms"
                    element={
                      <RouteErrorBoundary>
                        <Rooms />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/rooms/:areaSlug"
                    element={
                      <RouteErrorBoundary>
                        <AreaRooms />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/map"
                    element={
                      <RouteErrorBoundary>
                        <Map />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/chat"
                    element={
                      <RouteErrorBoundary>
                        <Chat />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/roommates"
                    element={
                      <RouteErrorBoundary>
                        <Roommates />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/services"
                    element={
                      <RouteErrorBoundary>
                        <Services />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/dashboard"
                    element={
                      <RouteErrorBoundary>
                        <Dashboard />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/payment/status"
                    element={
                      <RouteErrorBoundary>
                        <PaymentStatus />
                      </RouteErrorBoundary>
                    }
                  />
                  <Route
                    path="/auth"
                    element={
                      <RouteErrorBoundary>
                        <Auth />
                      </RouteErrorBoundary>
                    }
                  />
                </Route>
              </Routes>
            </Suspense>
          </BrowserRouter>
        </ErrorBoundary>
        <Toaster richColors position="top-right" />
        <PwaBanners />
      </AppProvider>
      {import.meta.env.DEV && <ReactQueryDevtools initialIsOpen={false} />}
    </QueryClientProvider>
  );
}
