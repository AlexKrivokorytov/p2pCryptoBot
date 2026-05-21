import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Clock, ShieldAlert, CreditCard } from "lucide-react";
import { marketplaceApi } from "../api/client";
import { useAppStore } from "../store/useAppStore";
import {
  tgBackButtonShow,
  tgHapticSuccess,
  tgMainButtonShow,
  tgMainButtonHide,
  tgMainButtonShowProgress,
  tgMainButtonHideProgress,
  tgMainButtonOnClick,
} from "../lib/tg";

interface DealDetails {
  id: string;
  status: string;
  amount: number;
  currency_type: string;
  payment_method?: string;
  payment_account?: string;
  payment_name?: string;
  blockchain?: string;
  network?: string;
  escrow_wallet_address?: string;
  tx_hash_deposit?: string;
  error?: string;
}

export function Checkout() {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const { setIsLoading, isLoading } = useAppStore();
  const [deal, setDeal] = useState<DealDetails | null>(null);

  useEffect(() => {
    return tgBackButtonShow(() => navigate(-1));
  }, [navigate]);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        if (dealId) {
          const data = await marketplaceApi.getDeal(dealId);
          setDeal(data as DealDetails);
        }
      } catch {
        setDeal(null);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [dealId, setIsLoading]);

  useEffect(() => {
    if (!deal || deal.status !== "created") return;

    tgMainButtonShow({ text: "✅ I HAVE PAID", color: "#2ea6ff", textColor: "#ffffff" });

    const off = tgMainButtonOnClick(async () => {
      try {
        tgMainButtonShowProgress();
        await marketplaceApi.markDealPaid(deal.id);
        tgHapticSuccess();
        alert("Payment confirmed! Seller has been notified.");
        navigate("/deals");
      } catch {
        alert("Failed to confirm payment. Please try again.");
      } finally {
        tgMainButtonHideProgress();
      }
    });

    return () => {
      off();
      tgMainButtonHide();
    };
  }, [deal, navigate]);

  if (isLoading) return <div className="p-4 animate-pulse h-screen" />;
  if (!deal || deal.error) return <div className="p-4 text-center">Deal not found.</div>;

  return (
    <div
      className="flex flex-col min-h-screen p-4 pb-24"
      style={{ background: "var(--tg-theme-bg-color, #fff)" }}
    >
      <div className="text-center mb-6 mt-4">
        <h1 className="text-2xl font-bold mb-1">Secure Checkout</h1>
        <p className="text-sm flex items-center justify-center opacity-60">
          <ShieldAlert className="w-4 h-4 mr-1" /> Fiat Escrow — funds released after confirmation
        </p>
      </div>

      <div className="p-4 rounded-2xl shadow-sm mb-4" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
        <div className="flex justify-between items-center mb-4 pb-4" style={{ borderBottom: "1px solid rgba(0,0,0,0.08)" }}>
          <span className="opacity-60 font-medium">Amount to pay</span>
          <span className="text-2xl font-bold">
            {deal.currency_type === "CRYPTO" ? `${deal.amount} ${deal.blockchain?.toUpperCase()}` : `$${deal.amount}`}
          </span>
        </div>

        <h2 className="text-xs font-bold mb-3 uppercase tracking-wider opacity-50">
          {deal.currency_type === "CRYPTO" ? "Crypto Escrow Details" : "Transfer Details"}
        </h2>

        <div className="space-y-3 text-sm">
          {deal.currency_type === "CRYPTO" ? (
            <>
              <div className="flex items-center justify-between">
                <span className="opacity-60">Blockchain</span>
                <span className="font-semibold">{deal.blockchain?.toUpperCase()} ({deal.network})</span>
              </div>
              <div className="flex flex-col gap-2">
                <span className="opacity-60">Escrow Address</span>
                <div className="relative group">
                  <span className="font-mono break-all text-[11px] p-3 rounded-xl block leading-tight" 
                    style={{ background: "var(--tg-theme-bg-color, #fff)", border: "1px solid rgba(0,0,0,0.05)" }}>
                    {deal.escrow_wallet_address}
                  </span>
                  <button 
                    onClick={() => {
                      navigator.clipboard.writeText(deal.escrow_wallet_address || "");
                      tgHapticSuccess();
                    }}
                    className="absolute right-2 top-2 text-[10px] font-bold px-2 py-1 rounded bg-blue-500 text-white"
                  >
                    COPY
                  </button>
                </div>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <span className="opacity-60">Bank</span>
                <span className="font-semibold flex items-center">
                  <CreditCard className="w-4 h-4 mr-1 opacity-40" />
                  {deal.payment_method}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="opacity-60">Card Number</span>
                <span className="font-mono px-2 py-1 rounded text-sm" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
                  {deal.payment_account}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="opacity-60">Receiver Name</span>
                <span className="font-semibold">{deal.payment_name}</span>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="p-4 rounded-xl flex items-start text-sm"
        style={{ background: "rgba(255, 152, 0, 0.12)", color: "var(--tg-theme-text-color, #333)" }}>
        <Clock className="w-5 h-5 mr-3 shrink-0 mt-0.5 opacity-70" />
        <p>
          {deal.currency_type === "CRYPTO" 
            ? "Send the exact amount to the escrow address. Payment will be detected automatically within 1-5 minutes."
            : "Transfer the exact amount within 15 minutes. Do not add any comments to the bank transfer."}
        </p>
      </div>
    </div>
  );
}
