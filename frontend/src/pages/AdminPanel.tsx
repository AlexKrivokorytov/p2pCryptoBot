import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Shield, Check, AlertTriangle, MessageSquare } from "lucide-react";
import { marketplaceApi } from "../api/client";
import { useAppStore } from "../store/useAppStore";
import { tgHapticLight, tgHapticSuccess, tgHapticError, tgShowAlert, tgBackButtonShow } from "../lib/tg";

export function AdminPanel() {
  const [disputes, setDisputes] = useState<any[]>([]);
  const { setIsLoading, isLoading } = useAppStore();
  const navigate = useNavigate();

  useEffect(() => {
    return tgBackButtonShow(() => navigate(-1));
  }, [navigate]);

  useEffect(() => {
    loadDisputes();
  }, []);

  async function loadDisputes() {
    setIsLoading(true);
    try {
      const data = await marketplaceApi.getAdminDisputes();
      setDisputes(data);
    } catch (e: any) {
      if (e.response?.status === 403) {
        await tgShowAlert("Access Denied. You are not an admin.");
        navigate("/");
      }
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleResolve(dealId: string, resolution: "buyer" | "seller") {
    const comment = prompt("Enter resolution comment (optional):") || "";
    setIsLoading(true);
    try {
      await marketplaceApi.resolveAdminDispute(dealId, resolution, comment);
      tgHapticSuccess();
      await tgShowAlert(`Dispute resolved in favor of ${resolution}`);
      loadDisputes();
    } catch (e: any) {
      tgHapticError();
      await tgShowAlert(e.response?.data?.detail || "Failed to resolve dispute");
    } finally {
      setIsLoading(false);
    }
  }

  if (isLoading && disputes.length === 0) return <div className="p-4">Loading disputes...</div>;

  return (
    <div className="flex flex-col h-full" style={{ minHeight: "100vh", background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
      <div className="p-4 mb-2 shadow-sm" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
        <h1 className="text-xl font-bold flex items-center gap-2 text-red-500">
          <Shield className="w-6 h-6" /> Admin Panel
        </h1>
        <p className="text-sm opacity-70">Manage active marketplace disputes</p>
      </div>

      <div className="px-4 pb-20 mt-2">
        {disputes.length === 0 ? (
          <div className="text-center p-8 opacity-50">
            <Check className="w-12 h-12 mx-auto mb-2 text-green-500" />
            <p>No active disputes</p>
          </div>
        ) : (
          <div className="space-y-4">
            {disputes.map((d) => (
              <div key={d.id} className="p-4 rounded-2xl shadow-sm" style={{ background: "var(--tg-theme-bg-color, #fff)", border: "1px solid #fecaca" }}>
                <div className="flex justify-between items-start mb-2">
                  <div>
                    <h2 className="font-bold text-sm">Deal #{d.id.substring(0, 8)}</h2>
                    <p className="text-xs opacity-70">{new Date(d.dispute_opened_at).toLocaleString()}</p>
                  </div>
                  <span className="text-red-600 font-bold bg-red-50 px-2 py-1 rounded text-xs flex items-center gap-1 border border-red-200">
                    <AlertTriangle className="w-3 h-3" /> DISPUTE
                  </span>
                </div>

                <div className="mb-4 p-3 bg-red-50 rounded-lg text-sm border border-red-100" style={{ color: "#7f1d1d" }}>
                  <p className="font-semibold text-xs opacity-60 mb-1 uppercase tracking-wider">Reason</p>
                  <p>{d.dispute_reason || "No reason provided"}</p>
                </div>

                <div className="flex justify-between items-center mb-4">
                  <span className="font-mono font-bold text-lg">{d.amount} {d.currency}</span>
                  <button
                    onClick={() => { tgHapticLight(); navigate(`/chat/${d.id}`); }}
                    className="flex items-center gap-1 text-sm font-semibold px-3 py-1.5 rounded-lg"
                    style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff" }}
                  >
                    <MessageSquare className="w-4 h-4" /> View Chat
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => handleResolve(d.id, "buyer")}
                    className="py-2.5 px-3 bg-red-100 text-red-700 font-bold text-sm rounded-lg transition-opacity active:opacity-60"
                  >
                    Refund Buyer
                  </button>
                  <button
                    onClick={() => handleResolve(d.id, "seller")}
                    className="py-2.5 px-3 bg-green-100 text-green-700 font-bold text-sm rounded-lg transition-opacity active:opacity-60"
                  >
                    Pay Seller
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
