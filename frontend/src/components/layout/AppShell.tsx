import Sidebar from "./Sidebar"

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-[#050505] text-[#e4e4e7]">
      <Sidebar />
      <main className="flex-1 min-w-0 p-4 md:p-6 pt-14 md:pt-6 overflow-y-auto scrollbar-thin">
        {children}
      </main>
    </div>
  )
}
