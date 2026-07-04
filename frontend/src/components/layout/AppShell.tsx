import Sidebar from "./Sidebar"

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen bg-[#050505] text-[#e4e4e7]">
      <Sidebar />
      <main className="flex-1 p-6 overflow-y-auto scrollbar-thin">
        {children}
      </main>
    </div>
  )
}
