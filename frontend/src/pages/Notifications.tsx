import { useEffect, useState } from "react";
import { ArrowLeft, Bell } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { tgHapticLight } from "../lib/tg";
import { marketplaceApi } from "../api/client";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export function NotificationsPage() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadNotifications();
  }, []);

  async function loadNotifications() {
    try {
      const data = await marketplaceApi.getNotifications();
      setNotifications(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function markAsRead(id: string) {
    try {
      await marketplaceApi.markNotificationRead(id);
      setNotifications(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n));
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-[#1c1c1e] text-black dark:text-white">
      {/* Header */}
      <div className="flex items-center px-4 py-3 border-b border-gray-200 dark:border-gray-800 shrink-0">
        <button
          onClick={() => { tgHapticLight(); navigate(-1); }}
          className="p-1 -ml-1 mr-3 rounded-full hover:bg-black/5 dark:hover:bg-white/10"
        >
          <ArrowLeft className="w-6 h-6" />
        </button>
        <h1 className="text-xl font-bold flex-1">Notifications</h1>
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading ? (
          <div className="flex justify-center p-8 opacity-50"><Bell className="w-8 h-8 animate-pulse" /></div>
        ) : notifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 opacity-50">
            <Bell className="w-12 h-12 mb-3" />
            <p>No notifications yet.</p>
          </div>
        ) : (
          notifications.map(n => (
            <div
              key={n.id}
              onClick={() => { if (!n.is_read) markAsRead(n.id); }}
              className={`p-3 rounded-2xl ${n.is_read ? 'bg-gray-100 dark:bg-gray-800/50' : 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800'}`}
            >
              <div className="flex justify-between items-start mb-1">
                <h3 className="font-semibold text-sm">{n.title}</h3>
                {!n.is_read && <span className="w-2 h-2 bg-blue-500 rounded-full mt-1 shrink-0"></span>}
              </div>
              <p className="text-sm opacity-80">{n.message}</p>
              <span className="text-[10px] opacity-50 mt-2 block">
                {new Date(n.created_at).toLocaleString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
