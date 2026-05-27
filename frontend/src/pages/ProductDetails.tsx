import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Star, Download, ShieldCheck, User } from "lucide-react";
import type { Product } from "../api/client";
import { marketplaceApi } from "../api/client";
import { useAppStore } from "../store/useAppStore";
import {
  tgBackButtonShow,
  tgHapticSuccess,
  tgHapticError,
  tgMainButtonShow,
  tgMainButtonHide,
  tgMainButtonShowProgress,
  tgMainButtonHideProgress,
  tgMainButtonOnClick,
  tgOpenInvoice,
  tgShowAlert,
} from "../lib/tg";

// ─── Constants ────────────────────────────────────────────────────────────────

const CATEGORY_GRADIENTS: Record<string, string> = {
  mentorship: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
  design:     "linear-gradient(135deg, #f093fb 0%, #f5576c 100%)",
  social:     "linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)",
  education:  "linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)",
  digital:    "linear-gradient(135deg, #fa709a 0%, #fee140 100%)",
};

const CATEGORY_EMOJI: Record<string, string> = {
  mentorship: "🎓", design: "🎨", social: "📱", education: "📚", digital: "💻",
};

const MOCK_PRODUCTS: Product[] = [
  { id: "1", seller_id: 1, title: "Premium Mentorship", description: "1 month of 1-on-1 crypto mentorship with weekly calls and daily chat support. Includes private Telegram group access, trade review sessions, and personalized portfolio strategy.", price: 500, currency_type: "XTR", is_digital: true, category: "mentorship" },
  { id: "2", seller_id: 1, title: "Web3 UI Kit", description: "Complete Figma UI kit for Web3 apps with 200+ components. Includes light/dark variants and auto-layout.", price: 50, currency_type: "FIAT", fiat_currency: "USD", is_digital: true, category: "design" },
  { id: "3", seller_id: 1, title: "Figma Templates Pack", description: "50 premium Figma templates for SaaS and marketplace products. Free updates forever.", price: 0.5, currency_type: "CRYPTO", crypto_asset: "TON", is_digital: true, category: "design" },
  { id: "4", seller_id: 1, title: "Social Media Pack", description: "200 ready-made posts for Instagram, Telegram and Twitter.", price: 200, currency_type: "XTR", is_digital: true, category: "social" },
  { id: "5", seller_id: 1, title: "Crypto Course Beginner", description: "Full beginner crypto trading course with 8 hours of HD video.", price: 99, currency_type: "FIAT", fiat_currency: "USD", is_digital: true, category: "education" },
  { id: "6", seller_id: 1, title: "Telegram Bot Template", description: "Ready-to-deploy Python Telegram bot with Stars payment integration.", price: 1.5, currency_type: "CRYPTO", crypto_asset: "TON", is_digital: true, category: "digital" },
];

// ─── Component ────────────────────────────────────────────────────────────────

export function ProductDetails() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { setIsLoading, isLoading } = useAppStore();
  const [product, setProduct] = useState<Product | null>(null);

  const [promoCodeInput, setPromoCodeInput] = useState("");
  const [appliedPromo, setAppliedPromo] = useState<{ code: string; discount_type: string; discount_value: number } | null>(null);
  const [promoError, setPromoError] = useState("");
  const [isApplyingPromo, setIsApplyingPromo] = useState(false);

  // Back button
  useEffect(() => {
    return tgBackButtonShow(() => navigate(-1));
  }, [navigate]);

  // Load product by ID — falls back to mock data if API unavailable
  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const data = await marketplaceApi.getProduct(id ?? "");
        setProduct(data);
      } catch {
        setProduct(MOCK_PRODUCTS.find((p) => p.id === id) ?? MOCK_PRODUCTS[0]);
      } finally {
        setIsLoading(false);
      }
    }
    if (id) load();
  }, [id, setIsLoading]);

  // Main button wiring depends on currency type
  useEffect(() => {
    if (!product) return;

    let finalPrice = product.price;
    if (appliedPromo) {
      if (appliedPromo.discount_type === "percentage") {
        finalPrice = finalPrice - (finalPrice * appliedPromo.discount_value) / 100;
      } else {
        finalPrice = finalPrice - appliedPromo.discount_value;
      }
      if (finalPrice < 0) finalPrice = 0;
    }

    tgMainButtonShow({
      text: product.currency_type === "XTR"
        ? `⭐ PAY ${finalPrice} STARS`
        : `💳 BUY FOR ${product.currency_type === "CRYPTO" ? `${finalPrice} ${product.crypto_asset}` : `$${finalPrice}`}`,
      color: product.currency_type === "XTR" ? "#E8A317" : "#2ea6ff",
      textColor: "#ffffff",
    });

    const off = tgMainButtonOnClick(async () => {
      tgMainButtonShowProgress();
      try {
        if (product.currency_type === "XTR") {
          const { invoice_url } = await marketplaceApi.createStarsInvoice(product.id, appliedPromo?.code);
          const status = await tgOpenInvoice(invoice_url);

          if (status === "paid") {
            await marketplaceApi.confirmStarsDeal(product.id, "");
            tgHapticSuccess();
            await tgShowAlert("✅ Payment successful! Check 'My Deals' for your purchase.");
            navigate("/deals");
          } else if (status === "cancelled") {
            tgHapticError();
          } else {
            tgHapticError();
            await tgShowAlert(`Payment ${status}. Please try again.`);
          }
        } else {
          const res = await marketplaceApi.createDeal(product.id, appliedPromo?.code);
          navigate(`/checkout/${res.id}`);
        }
      } catch (err: any) {
        tgHapticError();
        await tgShowAlert(err?.response?.data?.detail || "Something went wrong. Please try again.");
      } finally {
        tgMainButtonHideProgress();
      }
    });

    return () => { off(); tgMainButtonHide(); };
  }, [product, navigate, appliedPromo]);

  const handleApplyPromo = async () => {
    if (!promoCodeInput.trim() || !product) return;
    setIsApplyingPromo(true);
    setPromoError("");
    try {
      const res = await marketplaceApi.validatePromoCode(promoCodeInput.trim(), product.id);
      if (res.valid) {
        setAppliedPromo({ code: promoCodeInput.trim(), discount_type: res.discount_type, discount_value: res.discount_value });
        tgHapticSuccess();
      }
    } catch (err: any) {
      tgHapticError();
      setPromoError(err?.response?.data?.detail || "Invalid promo code");
      setAppliedPromo(null);
    } finally {
      setIsApplyingPromo(false);
    }
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  if (isLoading) {
    return (
      <div style={{ background: "var(--tg-theme-bg-color, #fff)", minHeight: "100vh" }}>
        <div className="animate-pulse" style={{ height: 240, background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
        <div className="p-4 space-y-3 animate-pulse">
          <div className="h-6 rounded-lg w-3/4" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
          <div className="h-4 rounded w-1/4" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
          <div className="h-24 rounded-xl" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
        </div>
      </div>
    );
  }

  if (!product) return <div className="p-4 text-center opacity-50">Product not found.</div>;

  const gradient = CATEGORY_GRADIENTS[product.category ?? ""] ?? "linear-gradient(135deg, #667eea 0%, #764ba2 100%)";
  const emoji = CATEGORY_EMOJI[product.category ?? ""] ?? "📦";

  return (
    <div
      className="flex flex-col pb-28"
      style={{ minHeight: "100vh", background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}
    >
      {/* Hero */}
      {product.image_urls && product.image_urls.length > 0 ? (
        <div className="relative w-full h-[300px] overflow-x-auto snap-x snap-mandatory flex scrollbar-hide" style={{ scrollbarWidth: 'none' }}>
          {product.image_urls.map((url, i) => (
            <div key={i} className="w-full h-full shrink-0 snap-center relative">
              <img
                src={`${import.meta.env.VITE_API_URL || ""}${url}`}
                alt={`${product.title} ${i + 1}`}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent pointer-events-none" />
              <div className="absolute top-4 right-4">
                <span
                  className="text-xs font-semibold px-3 py-1 rounded-full"
                  style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(8px)", color: "#fff" }}
                >
                  {product.is_digital ? "✨ Digital" : "📦 Physical"}
                </span>
              </div>
              {product.image_urls!.length > 1 && (
                <div className="absolute bottom-4 left-0 right-0 flex justify-center gap-1.5">
                  {product.image_urls!.map((_, dotIdx) => (
                    <div key={dotIdx} className={`h-1.5 rounded-full ${i === dotIdx ? 'w-4 bg-white' : 'w-1.5 bg-white/50'}`} />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="relative overflow-hidden" style={{ height: 240, background: gradient }}>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-8xl" style={{ filter: "drop-shadow(0 8px 24px rgba(0,0,0,0.2))" }}>{emoji}</span>
          </div>
          <div className="absolute top-4 right-4">
            <span
              className="text-xs font-semibold px-3 py-1 rounded-full"
              style={{ background: "rgba(255,255,255,0.2)", backdropFilter: "blur(8px)", color: "#fff" }}
            >
              {product.is_digital ? "✨ Digital" : "📦 Physical"}
            </span>
          </div>
        </div>
      )}

      <div className="p-4 space-y-4 flex-1">
        {/* Title + price */}
        <div className="flex items-start justify-between gap-2">
          <h1 className="text-xl font-bold leading-tight flex-1">{product.title}</h1>
          <div className="font-bold text-xl shrink-0 flex items-center" style={{ color: "var(--tg-theme-button-color, #5288c1)" }}>
            {product.currency_type === "XTR" && <><Star className="w-5 h-5 mr-1 fill-yellow-400 stroke-yellow-500" />{product.price}</>}
            {product.currency_type === "FIAT" && <>${product.price}</>}
            {product.currency_type === "CRYPTO" && <>{product.price} {product.crypto_asset}</>}
          </div>
        </div>

        {/* Feature pills */}
        <div className="flex flex-wrap gap-2">
          <span className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full font-medium" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
            <ShieldCheck className="w-3.5 h-3.5" style={{ color: "var(--tg-theme-button-color)" }} />
            Escrow protected
          </span>
          {product.is_digital && (
            <span className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full font-medium" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
              <Download className="w-3.5 h-3.5" style={{ color: "var(--tg-theme-button-color)" }} />
              Instant delivery
            </span>
          )}
          {product.currency_type === "XTR" && (
            <span className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-full font-medium" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
              <Star className="w-3.5 h-3.5 fill-yellow-400 stroke-yellow-500" />
              Telegram Stars
            </span>
          )}
        </div>

        {/* Description */}
        <div className="p-4 rounded-2xl" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
          <p className="text-[10px] font-bold mb-2 uppercase tracking-wider opacity-40">Description</p>
          <p className="text-sm leading-relaxed">{product.description}</p>
        </div>

        {/* Promo Code */}
        <div className="p-4 rounded-2xl" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
          <p className="text-[10px] font-bold mb-2 uppercase tracking-wider opacity-40">Promo Code</p>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Enter code"
              value={promoCodeInput}
              onChange={(e) => setPromoCodeInput(e.target.value)}
              className="flex-1 px-3 py-2 rounded-xl text-sm"
              style={{
                background: "var(--tg-theme-bg-color, #fff)",
                color: "var(--tg-theme-text-color, #000)",
                border: "1px solid var(--tg-theme-hint-color, #ccc)"
              }}
              disabled={!!appliedPromo}
            />
            {appliedPromo ? (
              <button
                onClick={() => { setAppliedPromo(null); setPromoCodeInput(""); setPromoError(""); }}
                className="px-4 py-2 rounded-xl text-sm font-semibold text-white bg-red-500"
              >
                Remove
              </button>
            ) : (
              <button
                onClick={handleApplyPromo}
                disabled={isApplyingPromo || !promoCodeInput.trim()}
                className="px-4 py-2 rounded-xl text-sm font-semibold text-white disabled:opacity-50"
                style={{ background: "var(--tg-theme-button-color, #5288c1)" }}
              >
                {isApplyingPromo ? "..." : "Apply"}
              </button>
            )}
          </div>
          {promoError && <p className="text-xs text-red-500 mt-2">{promoError}</p>}
          {appliedPromo && (
            <p className="text-xs text-green-500 mt-2">
              Discount applied: {appliedPromo.discount_type === "percentage" ? `${appliedPromo.discount_value}%` : `${appliedPromo.discount_value} off`}
            </p>
          )}
        </div>

        {/* Seller card */}
        <div className="p-4 rounded-2xl flex items-center gap-3" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
          <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0"
            style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff" }}>
            <User className="w-5 h-5" />
          </div>
          <div>
            <p className="text-sm font-semibold flex items-center gap-1">
              Seller
              {product.is_verified_seller && <ShieldCheck className="w-4 h-4" style={{ color: "var(--tg-theme-button-color, #5288c1)" }} />}
            </p>
            <p className="text-xs" style={{ color: "var(--tg-theme-hint-color, #999)" }}>
              ID #{product.seller_id} · ⭐ {product.seller_rating?.toFixed(1) || "5.0"} · {product.seller_reviews_count || 0} reviews
            </p>
          </div>
        </div>

        {/* Crypto Info */}
        {product.currency_type === "CRYPTO" && (
          <div className="p-4 rounded-2xl" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
            <p className="text-[10px] font-bold mb-2 uppercase tracking-wider opacity-40">Payment Info</p>
            <div className="flex items-center justify-between text-sm">
              <span className="opacity-60">Blockchain</span>
              <span className="font-semibold">{product.crypto_chain?.toUpperCase()}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
