import { TopNav } from "@/components/layout/top-nav";
import { NotificationProvider } from "@/components/notifications/notification-provider";
import { WsNotificationsBridge } from "@/components/notifications/ws-notifications-bridge";
import { CommandPalette } from "@/components/search/command-palette";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <NotificationProvider>
      <WsNotificationsBridge />
      <div
        className="flex flex-col h-screen overflow-hidden bg-palazzo"
      >
        {/* Global palazzo overlay — léger pour garder la lisibilité */}
        <div
          className="pointer-events-none fixed inset-0 z-0"
          style={{
            background: "linear-gradient(to bottom, rgba(5,5,5,0.70) 0%, rgba(5,5,5,0.82) 60%, rgba(5,5,5,0.90) 100%)",
          }}
        />
        <div className="relative z-10 flex flex-col h-full">
          <TopNav />
          <div className="flex flex-1 flex-col overflow-hidden">
            {children}
          </div>
        </div>
      </div>
      <CommandPalette />
    </NotificationProvider>
  );
}
