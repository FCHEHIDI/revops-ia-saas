import { Sidebar } from "@/components/layout/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex h-screen overflow-hidden"
      style={{ background: "var(--bg-base)" }}
    >
      <Sidebar />
      <div
        className="flex flex-1 flex-col overflow-hidden"
        style={{ background: "var(--bg-base)" }}
      >
        {children}
      </div>
    </div>
  );
}
