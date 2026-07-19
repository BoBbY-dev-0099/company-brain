import { createBrowserRouter, Navigate, Outlet } from "react-router-dom"
import Landing from "./pages/Landing"
import ApiKeys from "./pages/ApiKeys"
import Operations from "./pages/Operations"
import Connect from "./pages/Connect"
import Simulation from "./pages/Simulation"
import WorkflowPlayground from "./pages/WorkflowPlayground"
import IntegrationLab from "./pages/IntegrationLab"
import NexaFlowLab from "./pages/NexaFlowLab"
import MemoryLedger from "./pages/MemoryLedger"
import AppShell from "./components/layout/AppShell"

const router = createBrowserRouter([
  { path: "/", element: <Landing /> },
  { path: "/play/workflow", element: <WorkflowPlayground /> },
  { path: "/play/integration-lab", element: <IntegrationLab /> },
  { path: "/play/nexaflow", element: <NexaFlowLab /> },
  { path: "/play/:templateId", element: <Simulation /> },
  { path: "/sign-in", element: <Navigate to="/app/inbox" replace /> },
  { path: "/sign-in/*", element: <Navigate to="/app/inbox" replace /> },
  { path: "/sign-up", element: <Navigate to="/app/inbox" replace /> },
  { path: "/sign-up/*", element: <Navigate to="/app/inbox" replace /> },
  {
    path: "/app",
    element: (
      <AppShell>
        <Outlet />
      </AppShell>
    ),
    children: [
      { index: true, element: <Navigate to="/" replace /> },
      { path: "inbox", element: <Navigate to="/" replace /> },
      { path: "audit", element: <Operations /> },
      { path: "connect", element: <Connect /> },
      { path: "memory", element: <MemoryLedger /> },
      { path: "api-keys", element: <ApiKeys /> },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
])

export default router
