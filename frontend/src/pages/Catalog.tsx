import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Star } from "lucide-react";
import type { Product } from "../api/client";
import { marketplaceApi } from "../api/client";
import { useAppStore } from "../store/useAppStore";
import { tgHapticLight } from "../lib/tg";

const CATEGORIES = [
  { key: "", label: "All" },
  { key: "digital", label: "Digital" },
  { key: "mentorship", label: "Mentoring" },
  { key: "design", label: "Design" },
  { key: "social", label: "Social" },
  { key: "education", label: "Courses" },
];

const MOCK_PRODUCTS: Product[] = [
  { id: "1", seller_id: 1, title: "Premium Mentorship", description: "1 month of 1-on-1 crypto mentorship with weekly calls and daily chat support.", price: 500, currency_type: "XTR", is_digital: true, category: "mentorship" },
  { id: "2", seller_id: 1, title: "Web3 UI Kit", description: "Complete Figma UI kit for Web3 apps with 200+ components.", price: 50, currency_type: "FIAT", fiat_currency: "USD", is_digital: true, category: "design" },
  { id: "3", seller_id: 1, title: "Figma Templates Pack", description: "50 premium Figma templates for SaaS and marketplaces.", price: 0.5, currency_type: "CRYPTO", crypto_asset: "TON", is_digital: true, category: "design" },
  { id: "4", seller_id: 1, title: "Social Media Pack", description: "200 ready-made posts for Instagram, Telegram and Twitter.", price: 200, currency_type: "XTR", is_digital: true, category: "social" },
  { id: "5", seller_id: 1, title: "Crypto Course Beginner", description: "Full beginner crypto trading course with 8 hours of video.", price: 99, currency_type: "FIAT", fiat_currency: "USD", is_digital: true, category: "education" },
  { id: "6", seller_id: 1, title: "Telegram Bot Template", description: "Ready-to-deploy Python Telegram bot with payment integration.", price: 1.5, currency_type: "CRYPTO", crypto_asset: "TON", is_digital: true, category: "digital" },
];

const EMOJI_MAP: Record<string, string> = {
  mentorship: "🎓",
  design: "🎨",
  social: "📱",
  education: "📚",
  digital: "💻",
};

function getEmoji(product: Product): string {
  if (product.category && EMOJI_MAP[product.category]) return EMOJI_MAP[product.category];
  if (product.currency_type === "XTR") return "⭐";
  if (product.currency_type === "CRYPTO") return "💎";
  return "🛍️";
}

function PriceTag({ product }: { product: Product }) {
  if (product.currency_type === "XTR")
    return <span className="flex items-center"><Star className="w-3.5 h-3.5 mr-0.5 fill-yellow-400 stroke-yellow-500" />{product.price}</span>;
  if (product.currency_type === "FIAT")
    return <span>${product.price}</span>;
  return <span>{product.price} {product.crypto_asset}</span>;
}

function SkeletonCard() {
  return (
    <div className="rounded-2xl overflow-hidden animate-pulse" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
      <div className="aspect-square" style={{ background: "var(--tg-theme-hint-color, #ccc)", opacity: 0.3 }} />
      <div className="p-3 space-y-2">
        <div className="h-3 rounded" style={{ background: "var(--tg-theme-hint-color, #ccc)", opacity: 0.3, width: "80%" }} />
        <div className="h-3 rounded" style={{ background: "var(--tg-theme-hint-color, #ccc)", opacity: 0.2, width: "50%" }} />
      </div>
    </div>
  );
}

export function Catalog() {
  const [allProducts, setAllProducts] = useState<Product[]>([]);
  const [category, setCategory] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("rating_desc");
  const { setIsLoading, isLoading } = useAppStore();

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      try {
        const data = await marketplaceApi.getProducts({ sort });
        setAllProducts(data);
      } catch {
        setAllProducts(MOCK_PRODUCTS);
      } finally {
        setIsLoading(false);
      }
    }
    load();
  }, [setIsLoading, sort]);

  const displayed = allProducts.filter((p) => {
    const matchesCat = !category || p.category === category;
    const matchesSearch = !search || p.title.toLowerCase().includes(search.toLowerCase()) || p.description?.toLowerCase().includes(search.toLowerCase());
    return matchesCat && matchesSearch;
  });

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
      {/* Search Bar */}
      <div className="px-4 mb-3">
        <div
          className="flex items-center gap-2 px-3 py-2 rounded-xl"
          style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}
        >
          <span className="opacity-40 text-lg">🔍</span>
          <input
            type="text"
            placeholder="Search marketplace..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="flex-1 bg-transparent border-none outline-none text-sm"
            style={{ color: "var(--tg-theme-text-color, #000)" }}
          />
          {search && (
            <button
                onClick={() => setSearch("")}
                className="bg-transparent border-none text-xs font-bold opacity-40 px-1"
                style={{ color: "var(--tg-theme-text-color, #000)" }}
            >
                Clear
            </button>
          )}
        </div>
        <div className="flex justify-between items-center mt-2 px-1">
          <span className="text-xs opacity-50 font-medium">Sort by:</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="bg-transparent border-none outline-none text-xs font-semibold"
            style={{ color: "var(--tg-theme-button-color, #5288c1)" }}
          >
            <option value="rating_desc">Highest Rated</option>
            <option value="newest">Newest</option>
            <option value="price_asc">Price: Low to High</option>
            <option value="price_desc">Price: High to Low</option>
          </select>
        </div>
      </div>

      {/* Category pills */}
      <div className="flex gap-2 px-4 pb-3 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        {CATEGORIES.map((cat) => {
          const active = category === cat.key;
          return (
            <button
              key={cat.key}
              onClick={() => { tgHapticLight(); setCategory(cat.key); }}
              className="shrink-0 px-3 py-1.5 rounded-full text-sm font-medium transition-all"
              style={{
                background: active ? "var(--tg-theme-button-color, #5288c1)" : "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                color: active ? "var(--tg-theme-button-text-color, #fff)" : "var(--tg-theme-text-color, #000)",
                border: "none",
                cursor: "pointer",
              }}
            >
              {cat.label}
            </button>
          );
        })}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {isLoading ? (
          <div className="grid grid-cols-2 gap-3">
            {[1, 2, 3, 4].map((i) => <SkeletonCard key={i} />)}
          </div>
        ) : displayed.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 opacity-50">
            <span className="text-5xl mb-3">🔍</span>
            <p className="text-sm">No products in this category</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {displayed.map((product) => (
              <Link
                key={product.id}
                to={`/product/${product.id}`}
                onClick={tgHapticLight}
                style={{
                  textDecoration: "none",
                  color: "var(--tg-theme-text-color, #000)",
                  background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                  borderRadius: "16px",
                  overflow: "hidden",
                  display: "block",
                }}
                className="active:scale-95 transition-transform"
              >
                <div className="relative">
                  {product.is_promoted && (
                    <div className="absolute top-2 left-2 bg-yellow-500 text-white text-[10px] font-bold px-1.5 py-0.5 rounded shadow-sm z-10 flex items-center gap-0.5">
                      🚀 Ad
                    </div>
                  )}
                  <div
                    className="aspect-square flex items-center justify-center overflow-hidden"
                  style={{ background: "var(--tg-theme-bg-color, #fff)" }}
                >
                  {product.image_urls && product.image_urls.length > 0 ? (
                    <img
                      src={`${import.meta.env.VITE_API_URL || ""}${product.image_urls[0]}`}
                      alt={product.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-4xl">{getEmoji(product)}</span>
                  )}
                  </div>
                </div>
                <div className="p-3">
                  <p className="font-semibold text-sm leading-tight mb-1.5" style={{ display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                    {product.title}
                  </p>
                  <p className="font-bold text-sm flex items-center" style={{ color: "var(--tg-theme-button-color, #5288c1)" }}>
                    <PriceTag product={product} />
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
