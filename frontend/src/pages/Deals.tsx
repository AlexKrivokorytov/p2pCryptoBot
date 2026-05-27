import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Star } from "lucide-react";
import type { Deal } from "../api/client";
import { marketplaceApi } from "../api/client";
import { tgHapticLight } from "../lib/tg";
import { DisputeModal } from "../components/DisputeModal";

const MOCK_DEALS: Deal[] = [
  { id: "deal-1", status: "paid", amount: 500, currency_type: "XTR", product_title: "Premium Mentorship", role: "buyer" },
  { id: "deal-2", status: "created", amount: 50, currency_type: "FIAT", product_title: "Web3 UI Kit", role: "seller" },
  { id: "deal-3", status: "completed", amount: 0.5, currency_type: "CRYPTO", product_title: "Figma Templates Pack", role: "buyer" },
];

const STATUS_CONFIG: Record<string, { label: string; bg: string; color: string }> = {
  created:   { label: "Awaiting payment", bg: "rgba(255,152,0,0.12)", color: "#e65100" },
  paid:      { label: "Paid — confirm?",  bg: "rgba(33,150,243,0.12)", color: "#0277bd" },
  delivered: { label: "Delivered",        bg: "rgba(33,150,243,0.12)", color: "#0277bd" },
  completed: { label: "Completed",        bg: "rgba(76,175,80,0.12)",  color: "#2e7d32" },
  confirmed: { label: "Completed",        bg: "rgba(76,175,80,0.12)",  color: "#2e7d32" },
  dispute:   { label: "Disputed",         bg: "rgba(244,67,54,0.12)",  color: "#b71c1c" },
  cancelled: { label: "Cancelled",        bg: "rgba(158,158,158,0.12)", color: "#616161" },
};

function DealPrice({ deal }: { deal: Deal }) {
  if (deal.currency_type === "XTR")
    return <span className="flex items-center font-bold"><Star className="w-3.5 h-3.5 mr-0.5 fill-yellow-400 stroke-yellow-500" />{deal.amount}</span>;
  if (deal.currency_type === "FIAT") return <span className="font-bold">${deal.amount}</span>;
  return <span className="font-bold">{deal.amount} TON</span>;
}

export function DealsPage() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"all" | "buyer" | "seller">("all");
  const [reviewingDealId, setReviewingDealId] = useState<string | null>(null);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [disputingDealId, setDisputingDealId] = useState<string | null>(null);

  const loadDeals = async () => {
    setLoading(true);
    try {
      const data = await marketplaceApi.getMyDeals();
      setDeals(data);
    } catch {
      setDeals(MOCK_DEALS);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDeals();
  }, []);

  const filtered = tab === "all" ? deals : deals.filter((d) => d.role === tab);

  const handleReviewSubmit = async () => {
    if (!reviewingDealId) return;
    setIsSubmittingReview(true);
    try {
      await marketplaceApi.createReview(reviewingDealId, rating, comment);
      setReviewingDealId(null);
      setComment("");
      setRating(5);
      tgHapticLight();
    } catch (err: any) {
      if (err.response?.status === 409) {
        alert("You already reviewed this deal.");
        setReviewingDealId(null);
      } else {
        alert("Failed to submit review.");
      }
    } finally {
      setIsSubmittingReview(false);
    }
  };

  const handleDeliver = async (dealId: string) => {
    if (!confirm("Mark this item as delivered?")) return;
    try {
      await marketplaceApi.deliverDeal(dealId);
      const data = await marketplaceApi.getMyDeals();
      setDeals(data);
      tgHapticLight();
    } catch {
      alert("Failed to mark as delivered.");
    }
  };

  const handleComplete = async (dealId: string) => {
    if (!confirm("Confirm you received the item? This will release funds to the seller.")) return;
    try {
      await marketplaceApi.completeDeal(dealId);
      const data = await marketplaceApi.getMyDeals();
      setDeals(data);
      tgHapticLight();
    } catch {
      alert("Failed to complete deal.");
    }
  };

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
      {/* Header */}
      <div className="px-4 pt-4 pb-3">
        <h1 className="text-2xl font-bold">My Deals</h1>
      </div>

      {/* Tabs */}
      <div
        className="mx-4 mb-3 flex rounded-xl p-0.5"
        style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}
      >
        {(["all", "buyer", "seller"] as const).map((t) => (
          <button
            key={t}
            onClick={() => { tgHapticLight(); setTab(t); }}
            className="flex-1 py-1.5 text-sm font-medium rounded-lg transition-all"
            style={{
              background: tab === t ? "var(--tg-theme-bg-color, #fff)" : "transparent",
              color: "var(--tg-theme-text-color, #000)",
              border: "none",
              cursor: "pointer",
              boxShadow: tab === t ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
            }}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 rounded-2xl animate-pulse" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 opacity-40">
            <span className="text-5xl mb-3">📋</span>
            <p className="text-sm">No deals yet</p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((deal) => {
              const status = STATUS_CONFIG[deal.status] ?? STATUS_CONFIG.cancelled;
              const canReview = deal.role === "buyer" && ["completed"].includes(deal.status);
              const canDeliver = deal.role === "seller" && deal.status === "paid";
              const canComplete = deal.role === "buyer" && deal.status === "delivered";
              const canChat = !["completed", "cancelled"].includes(deal.status);

              const canDispute = deal.role === "buyer" && ["paid", "delivered"].includes(deal.status) && (() => {
                if (!deal.created_at) return false;
                const elapsed = Date.now() - new Date(deal.created_at).getTime();
                return elapsed > 15 * 60 * 1000;
              })();

              return (
                <div key={deal.id} className="relative group">
                  <div className="flex flex-col gap-2 p-4 rounded-2xl transition-all"
                    style={{
                      background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                    }}
                  >
                    <Link
                      to={deal.status === "created" && deal.role === "buyer" ? `/checkout/${deal.id}` : "#"}
                      onClick={tgHapticLight}
                      className="flex items-center gap-3 no-underline"
                      style={{ color: "var(--tg-theme-text-color, #000)" }}
                    >
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold text-sm leading-tight truncate mb-1">{deal.product_title}</p>
                        <div className="flex items-center gap-2">
                          <span
                            className="text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider"
                            style={{ background: status.bg, color: status.color }}
                          >
                            {status.label}
                          </span>
                          <span className="text-[10px] uppercase font-bold tracking-wider" style={{ color: "var(--tg-theme-hint-color, #999)" }}>
                            {deal.role}
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0" style={{ color: "var(--tg-theme-button-color, #5288c1)" }}>
                        <DealPrice deal={deal} />
                      </div>
                    </Link>

                    {deal.status === "dispute" && (
                      <div className="mt-2 p-2 rounded-xl text-xs font-semibold" style={{ background: "rgba(244,67,54,0.1)", color: "#b71c1c" }}>
                        🔴 Dispute under review
                      </div>
                    )}
                    {deal.dispute_resolution && (
                      <div className="mt-2 p-2 rounded-xl text-xs font-semibold" style={{ background: "rgba(33,150,243,0.1)", color: "#0277bd" }}>
                        ℹ️ Dispute resolved: {deal.dispute_resolution}
                      </div>
                    )}

                    {/* Actions Row */}
                    {(canDeliver || canComplete || canChat || canReview || canDispute) && (
                      <div className="flex gap-2 mt-2 pt-3 border-t border-black/5">
                        {canDeliver && (
                          <button
                            onClick={() => handleDeliver(deal.id)}
                            className="flex-1 py-2 text-xs font-bold rounded-xl"
                            style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff", border: "none" }}
                          >
                            📦 Mark Delivered
                          </button>
                        )}
                        {canComplete && (
                          <button
                            onClick={() => handleComplete(deal.id)}
                            className="flex-1 py-2 text-xs font-bold rounded-xl"
                            style={{ background: "#2e7d32", color: "#fff", border: "none" }}
                          >
                            ✅ Confirm Receipt
                          </button>
                        )}
                        {canChat && (
                          <Link
                            to={`/chat/${deal.id}`}
                            className="flex-1 py-2 text-xs font-bold rounded-xl text-center no-underline"
                            style={{ background: "rgba(82, 136, 193, 0.1)", color: "var(--tg-theme-button-color, #5288c1)" }}
                          >
                            💬 Chat
                          </Link>
                        )}
                        {canReview && (
                          <button
                            onClick={() => setReviewingDealId(deal.id)}
                            className="flex-1 py-2 text-xs font-bold rounded-xl"
                            style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff", border: "none" }}
                          >
                            ⭐ Review
                          </button>
                        )}
                        {canDispute && (
                          <button
                            onClick={() => setDisputingDealId(deal.id)}
                            className="flex-1 py-2 text-xs font-bold rounded-xl"
                            style={{ background: "rgba(244,67,54,0.1)", color: "#b71c1c", border: "none" }}
                          >
                            ⚠️ Dispute
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Review Modal */}
      {reviewingDealId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-sm rounded-2xl p-5" style={{ background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}>
            <h3 className="text-lg font-bold mb-4 text-center">Leave a Review</h3>

            <div className="flex justify-center gap-2 mb-6">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  onClick={() => setRating(star)}
                  className="bg-transparent border-none outline-none focus:outline-none p-1"
                >
                  <Star
                    className={`w-8 h-8 ${rating >= star ? 'fill-yellow-400 stroke-yellow-500' : 'fill-transparent stroke-gray-300'}`}
                  />
                </button>
              ))}
            </div>

            <textarea
              className="w-full rounded-xl p-3 text-sm mb-4"
              style={{
                background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                color: "var(--tg-theme-text-color, #000)",
                border: "none",
                outline: "none"
              }}
              rows={3}
              placeholder="Optional comment..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />

            <div className="flex gap-2">
              <button
                onClick={() => setReviewingDealId(null)}
                className="flex-1 py-3 rounded-xl font-bold text-sm"
                style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", color: "var(--tg-theme-text-color, #000)" }}
              >
                Cancel
              </button>
              <button
                onClick={handleReviewSubmit}
                disabled={isSubmittingReview}
                className="flex-1 py-3 rounded-xl font-bold text-sm opacity-100 disabled:opacity-50"
                style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff" }}
              >
                {isSubmittingReview ? "Submitting..." : "Submit"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Dispute Modal */}
      {disputingDealId && (
        <DisputeModal
          dealId={disputingDealId}
          onClose={() => setDisputingDealId(null)}
          onSuccess={() => {
            setDisputingDealId(null);
            loadDeals();
          }}
        />
      )}
    </div>
  );
}
