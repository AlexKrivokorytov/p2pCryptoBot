import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { ShoppingBag, Star, Shield, ChevronRight, Bell } from "lucide-react";
import { tgHapticLight } from "../lib/tg";

interface StatCardProps {
  label: string;
  value: string;
  emoji: string;
}

function StatCard({ label, value, emoji }: StatCardProps) {
  return (
    <div
      className="flex-1 flex flex-col items-center justify-center py-4 rounded-2xl"
      style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}
    >
      <span className="text-2xl mb-1">{emoji}</span>
      <p className="font-bold text-lg leading-none">{value}</p>
      <p className="text-xs mt-0.5" style={{ color: "var(--tg-theme-hint-color, #999)" }}>{label}</p>
    </div>
  );
}

interface MenuRowProps {
  icon: React.ReactNode;
  label: string;
  sublabel?: string;
  onClick?: () => void;
  href?: string;
}

function MenuRow({ icon, label, sublabel, onClick }: MenuRowProps) {
  return (
    <button
      onClick={() => { tgHapticLight(); onClick?.(); }}
      className="w-full flex items-center gap-3 px-4 py-3.5 active:opacity-70 transition-opacity"
      style={{ background: "transparent", border: "none", cursor: "pointer", textAlign: "left" }}
    >
      <span className="text-lg">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium">{label}</p>
        {sublabel && <p className="text-xs" style={{ color: "var(--tg-theme-hint-color, #999)" }}>{sublabel}</p>}
      </div>
      <ChevronRight className="w-4 h-4 shrink-0" style={{ color: "var(--tg-theme-hint-color, #999)" }} />
    </button>
  );
}

export function ProfilePage() {
  const navigate = useNavigate();
  const tg = (window as any).Telegram?.WebApp;
  const user = tg?.initDataUnsafe?.user;
  const firstName = user?.first_name ?? "Guest";
  const username = user?.username ? `@${user.username}` : "Not set";
  const photoUrl = user?.photo_url;

  const [refStats, setRefStats] = useState<{ referral_balance: number; referred_users: number; referral_link: string } | null>(null);

  useEffect(() => {
    if (!tg?.initData) return;
    fetch("/api/referral/stats", {
      headers: { Authorization: `tma ${tg.initData}` }
    })
      .then((res) => res.json())
      .then((data) => {
        if (!data.detail) setRefStats(data);
      })
      .catch(console.error);
  }, [tg?.initData]);

  return (
    <div
      className="flex flex-col min-h-full pb-4"
      style={{ background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}
    >
      {/* Avatar + name */}
      <div className="flex flex-col items-center pt-8 pb-5 px-4">
        {photoUrl ? (
          <img src={photoUrl} className="w-20 h-20 rounded-full mb-3" alt="avatar" />
        ) : (
          <div
            className="w-20 h-20 rounded-full mb-3 flex items-center justify-center text-3xl font-bold"
            style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "var(--tg-theme-button-text-color, #fff)" }}
          >
            {firstName.charAt(0).toUpperCase()}
          </div>
        )}
        <h1 className="text-xl font-bold">{firstName}</h1>
        <p className="text-sm" style={{ color: "var(--tg-theme-hint-color, #999)" }}>{username}</p>
      </div>

      {/* Stats */}
      <div className="flex gap-3 px-4 mb-4">
        <StatCard label="Deals" value="3" emoji="🤝" />
        <StatCard label="Stars spent" value="700" emoji="⭐" />
        <StatCard label="Rating" value="5.0" emoji="⭐" />
      </div>

      {/* Seller section — navigates to dashboard */}
      <div className="mx-4 mb-3">
        <button
          onClick={() => { tgHapticLight(); navigate("/seller"); }}
          className="w-full flex items-center gap-3 p-4 rounded-2xl"
          style={{
            background: "var(--tg-theme-button-color, #5288c1)",
            color: "var(--tg-theme-button-text-color, #fff)",
            border: "none",
            cursor: "pointer",
            textAlign: "left",
          }}
        >
          <ShoppingBag className="w-6 h-6 shrink-0" />
          <div className="flex-1">
            <p className="font-semibold text-sm">My Products</p>
            <p className="text-xs opacity-80">Manage your listings and earnings</p>
          </div>
          <ChevronRight className="w-4 h-4 opacity-70" />
        </button>
      </div>

      {/* Referrals */}
      {refStats && (
        <div className="mx-4 mb-3 rounded-2xl p-4" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
          <h2 className="font-semibold text-sm mb-2 flex items-center gap-2"><span className="text-xl">🤝</span> My Referrals</h2>
          <div className="flex justify-between mb-2">
            <span className="text-xs opacity-70">Balance:</span>
            <span className="font-bold text-sm">${refStats.referral_balance.toFixed(2)}</span>
          </div>
          <div className="flex justify-between mb-4">
            <span className="text-xs opacity-70">Users invited:</span>
            <span className="font-bold text-sm">{refStats.referred_users}</span>
          </div>
          <button
            onClick={() => {
              tgHapticLight();
              tg?.openTelegramLink?.(`https://t.me/share/url?url=${encodeURIComponent(refStats.referral_link)}&text=Join%20P2P%20Marketplace`);
            }}
            className="w-full py-2.5 rounded-lg text-sm font-semibold transition-opacity active:opacity-70"
            style={{
              background: "var(--tg-theme-button-color, #5288c1)",
              color: "var(--tg-theme-button-text-color, #fff)",
              border: "none",
            }}
          >
            Share Invite Link
          </button>
        </div>
      )}

      {/* Menu */}
      <div className="mx-4 rounded-2xl overflow-hidden" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
        <MenuRow icon={<Star className="w-5 h-5 text-yellow-500" />} label="My Stars Balance" sublabel="Manage Telegram Stars" />
        <div style={{ height: "1px", background: "var(--tg-theme-bg-color, #fff)", margin: "0 16px" }} />
        <MenuRow icon={<Shield className="w-5 h-5" style={{ color: "var(--tg-theme-button-color)" }} />} label="Security & Privacy" sublabel="Payment methods and trust" />
        <div style={{ height: "1px", background: "var(--tg-theme-bg-color, #fff)", margin: "0 16px" }} />
        <MenuRow
          icon="📞"
          label="Support"
          sublabel="Chat with us in Telegram"
          onClick={() => tg?.openTelegramLink?.("https://t.me/your_support_bot")}
        />
        <div style={{ height: "1px", background: "var(--tg-theme-bg-color, #fff)", margin: "0 16px" }} />
        <MenuRow icon="📄" label="Terms of Service" />
        <div style={{ height: "1px", background: "var(--tg-theme-bg-color, #fff)", margin: "0 16px" }} />
        <MenuRow
          icon={<Bell className="w-5 h-5 text-purple-500" />}
          label="Notifications"
          sublabel="System and order alerts"
          onClick={() => navigate("/notifications")}
        />
        <MenuRow
          icon={<ShoppingBag className="w-5 h-5 text-blue-500" />}
          label="Seller Dashboard"
          sublabel="Manage products & promos"
          onClick={() => navigate("/seller")}
        />
        <div style={{ height: "1px", background: "var(--tg-theme-bg-color, #fff)", margin: "0 16px" }} />
        <MenuRow
          icon={<Shield className="w-5 h-5 text-red-500" />}
          label="Admin Panel"
          sublabel="Manage disputes"
          onClick={() => navigate("/admin")}
        />
      </div>


      <p className="text-center text-xs mt-6 opacity-30">P2P Marketplace v1.0</p>
    </div>
  );
}
