import { TopNav } from "@/components/layout/top-nav";
import { NotificationProvider } from "@/components/notifications/notification-provider";
import { CommandPalette } from "@/components/search/command-palette";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <NotificationProvider>
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
      <CommandPalette />
    </NotificationProvider>
  );
}
