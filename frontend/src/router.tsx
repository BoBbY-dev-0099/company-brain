import { createBrowserRouter, Navigate } from "react-router-dom"
import NexaFlowConsole from "./pages/NexaFlowConsole"
import NexaFlowSetup from "./pages/NexaFlowSetup"

const router = createBrowserRouter([
  { path: "/", element: <NexaFlowConsole /> },
  { path: "/setup", element: <NexaFlowSetup /> },
  // Legacy demo routes intentionally collapse to the single real-source story.
  { path: "*", element: <Navigate to="/" replace /> },
])

export default router
