import Sidebar from "./Sidebar"

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-[#f5f1e8] text-[#17212b]">
      <Sidebar />
      <main className="min-w-0 flex-1 overflow-y-auto p-4 pt-14 md:p-7 md:pt-7">
        {children}
      </main>
    </div>
  )
}
