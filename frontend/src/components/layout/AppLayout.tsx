import { Link, Outlet, useLocation } from "react-router-dom";
import { ShoppingBag, Search, ClipboardList, User } from "lucide-react";

const NAV_ITEMS = [
  { path: "/",        label: "Catalog", icon: ShoppingBag },
  { path: "/search",  label: "Search",  icon: Search },
  { path: "/deals",   label: "Deals",   icon: ClipboardList },
  { path: "/profile", label: "Profile", icon: User },
] as const;

export function AppLayout() {
  const location = useLocation();

  return (
    <div
      className="flex flex-col"
      style={{ height: "100%", background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}
    >
      {/* Page content — scrolls independently */}
      <main
        className="flex-1 overflow-y-auto scroll-area pb-nav"
        style={{ WebkitOverflowScrolling: "touch" } as React.CSSProperties}
      >
        <Outlet />
      </main>

      {/* Bottom Navigation Bar */}
      <nav
        className="fixed bottom-0 left-0 right-0 flex justify-around tap-highlight"
        style={{
          background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
          borderTop: "1px solid rgba(128,128,128,0.12)",
          paddingTop: "6px",
          paddingBottom: "calc(8px + var(--tg-safe-area-inset-bottom, env(safe-area-inset-bottom, 0px)))",
          zIndex: 100,
        }}
      >
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path;
          return (
            <Link
              key={path}
              to={path}
              className="flex flex-col items-center justify-center px-3 py-1 min-w-[56px]"
              style={{
                textDecoration: "none",
                color: active
                  ? "var(--tg-theme-button-color, #5288c1)"
                  : "var(--tg-theme-hint-color, #999)",
                transition: "color 0.15s ease",
              }}
            >
              <Icon
                className="w-6 h-6 mb-0.5"
                strokeWidth={active ? 2.5 : 1.8}
              />
              <span className="text-[10px] font-medium leading-none">{label}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
