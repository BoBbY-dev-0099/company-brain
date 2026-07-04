import { SignUp as ClerkSignUp } from "@clerk/clerk-react"
import { Sparkles } from "lucide-react"
import { Link } from "react-router-dom"

export default function SignUp() {
  return (
    <div className="min-h-screen bg-[#050505] text-[#e4e4e7] flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md space-y-6">
        <div className="flex items-center justify-center gap-2 text-[#22c55e]">
          <Sparkles className="w-6 h-6" />
          <span className="font-semibold text-xl">Company Brain</span>
        </div>
        <ClerkSignUp
          routing="path"
          path="/sign-up"
          signInUrl="/sign-in"
          afterSignUpUrl="/app/dashboard"
          appearance={{
            variables: {
              colorPrimary: "#22c55e",
              colorBackground: "#111114",
              colorText: "#e4e4e7",
              colorTextSecondary: "#7c7c8a",
              colorDanger: "#ef4444",
              fontFamily: "Inter, system-ui, sans-serif",
            },
          }}
        />
        <div className="text-center text-sm text-[#7c7c8a]">
          Already have an account?{" "}
          <Link to="/sign-in" className="text-[#22c55e] hover:underline">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  )
}
