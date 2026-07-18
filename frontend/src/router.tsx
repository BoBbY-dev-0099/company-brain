import { createBrowserRouter, Navigate, Outlet } from "react-router-dom"
import Landing from "./pages/Landing"
import Onboard from "./pages/Onboard"
import Dashboard from "./pages/Dashboard"
import Brain from "./pages/Brain"
import Intercepts from "./pages/Intercepts"
import Agents from "./pages/Agents"
import Events from "./pages/Events"
import Settings from "./pages/Settings"
import ApiKeys from "./pages/ApiKeys"
import AppShell from "./components/layout/AppShell"

const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/sign-in", element: <Navigate to="/app/dashboard" replace /> },
  { path: "/sign-in/*", element: <Navigate to="/app/dashboard" replace /> },
  { path: "/sign-up", element: <Navigate to="/app/dashboard" replace /> },
  { path: "/sign-up/*", element: <Navigate to="/app/dashboard" replace /> },
  {
    path: "/app",
    element: (
      <AppShell>
        <Outlet />
      </AppShell>
    ),
    children: [
      { index: true, element: <Navigate to="dashboard" replace /> },
      { path: "dashboard", element: <Dashboard /> },
      { path: "brain", element: <Brain /> },
      { path: "intercepts", element: <Intercepts /> },
      { path: "agents", element: <Agents /> },
      { path: "events", element: <Events /> },
      { path: "settings", element: <Settings /> },
      { path: "api-keys", element: <ApiKeys /> },
      { path: "onboard", element: <Onboard /> },
    ],
  },
])

export default router
