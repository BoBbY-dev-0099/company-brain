import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { ClerkProvider } from "@clerk/clerk-react"
import { RouterProvider } from "react-router-dom"
import router from "./router"
import "./index.css"

const PUBLISHABLE_KEY = (import.meta as any).env.VITE_CLERK_PUBLISHABLE_KEY
if (!PUBLISHABLE_KEY) {
  throw new Error("Missing VITE_CLERK_PUBLISHABLE_KEY")
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ClerkProvider
      publishableKey={PUBLISHABLE_KEY}
      afterSignOutUrl="/"
      appearance={{
        baseTheme: undefined,
        variables: {
          colorPrimary: "#22c55e",
          colorBackground: "#050505",
          colorText: "#e4e4e7",
          colorTextSecondary: "#7c7c8a",
          colorDanger: "#ef4444",
          colorSuccess: "#22c55e",
          fontFamily: "Inter, system-ui, sans-serif",
        },
      }}
    >
      <RouterProvider router={router} />
    </ClerkProvider>
  </StrictMode>,
)
