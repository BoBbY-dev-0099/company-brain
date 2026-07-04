import { useEffect } from "react"
import { useAuth } from "@clerk/clerk-react"
import { Navigate } from "react-router-dom"
import { setAuthTokenGetter } from "../../lib/api"

export default function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoaded, isSignedIn, getToken } = useAuth()

  // Set the token getter synchronously before rendering children so that
  // any child component that fires an API call on mount has a valid getter.
  useEffect(() => {
    setAuthTokenGetter(getToken)
  }, [getToken])
  if (isLoaded) {
    setAuthTokenGetter(getToken)
  }

  if (!isLoaded) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#050505] text-[#e4e4e7]">
        Loading…
      </div>
    )
  }

  if (!isSignedIn) {
    return <Navigate to="/sign-in" replace />
  }

  return <>{children}</>
}
