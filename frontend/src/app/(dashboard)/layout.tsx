import { TopNav } from "@/components/layout/top-nav";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex flex-col h-screen overflow-hidden"
      style={{ background: "var(--bg-base)" }}
    >
      <TopNav />
      <div
        className="flex flex-1 flex-col overflow-hidden"
        style={{ background: "var(--bg-base)" }}
      >
        {children}
      </div>
    </div>
  );
}
