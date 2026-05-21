import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { Search as SearchIcon, X } from "lucide-react";
import { Star } from "lucide-react";
import type { Product } from "../api/client";
import { marketplaceApi } from "../api/client";
import { tgHapticLight } from "../lib/tg";

const MOCK_PRODUCTS: Product[] = [
  { id: "1", seller_id: 1, title: "Premium Mentorship", description: "1 month of 1-on-1 crypto mentorship", price: 500, currency_type: "XTR", is_digital: true, category: "mentorship" },
  { id: "2", seller_id: 1, title: "Web3 UI Kit", description: "Figma UI kit for Web3 apps", price: 50, currency_type: "FIAT", fiat_currency: "USD", is_digital: true, category: "design" },
  { id: "3", seller_id: 1, title: "Figma Templates Pack", description: "50 premium Figma templates", price: 0.5, currency_type: "CRYPTO", crypto_asset: "TON", is_digital: true, category: "design" },
  { id: "4", seller_id: 1, title: "Social Media Pack", description: "200 ready-made posts", price: 200, currency_type: "XTR", is_digital: true, category: "social" },
  { id: "5", seller_id: 1, title: "Crypto Course Beginner", description: "Full beginner crypto course", price: 99, currency_type: "FIAT", fiat_currency: "USD", is_digital: true, category: "education" },
  { id: "6", seller_id: 1, title: "Telegram Bot Template", description: "Ready-to-deploy bot with payments", price: 1.5, currency_type: "CRYPTO", crypto_asset: "TON", is_digital: true, category: "digital" },
];

function PriceTag({ product }: { product: Product }) {
  if (product.currency_type === "XTR")
    return <span className="flex items-center"><Star className="w-3.5 h-3.5 mr-0.5 fill-yellow-400 stroke-yellow-500" />{product.price}</span>;
  if (product.currency_type === "FIAT") return <span>${product.price}</span>;
  return <span>{product.price} {product.crypto_asset}</span>;
}

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Product[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!query.trim()) {
      setResults([]);
      setSearched(false);
      return;
    }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await marketplaceApi.getProducts({ q: query });
        setResults(data);
      } catch {
        // Fallback: client-side mock search
        const q = query.toLowerCase();
        setResults(MOCK_PRODUCTS.filter(
          (p) => p.title.toLowerCase().includes(q) || p.description?.toLowerCase().includes(q)
        ));
      } finally {
        setLoading(false);
        setSearched(true);
      }
    }, 400);
  }, [query]);

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
      {/* Search bar */}
      <div className="p-4">
        <div
          className="flex items-center gap-2 px-3 rounded-xl"
          style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", height: "44px" }}
        >
          <SearchIcon className="w-4 h-4 shrink-0" style={{ color: "var(--tg-theme-hint-color, #999)" }} />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products..."
            className="flex-1 bg-transparent outline-none text-sm"
            style={{ color: "var(--tg-theme-text-color, #000)" }}
          />
          {query && (
            <button onClick={() => setQuery("")} className="shrink-0">
              <X className="w-4 h-4" style={{ color: "var(--tg-theme-hint-color, #999)" }} />
            </button>
          )}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        {!query && (
          <div className="flex flex-col items-center justify-center py-16 opacity-40">
            <span className="text-5xl mb-3">🔍</span>
            <p className="text-sm">Type to search products</p>
          </div>
        )}

        {loading && (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="flex gap-3 animate-pulse">
                <div className="w-16 h-16 rounded-xl shrink-0" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
                <div className="flex-1 py-1 space-y-2">
                  <div className="h-3 rounded" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", width: "70%" }} />
                  <div className="h-3 rounded" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", width: "40%" }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {!loading && searched && results.length === 0 && (
          <div className="flex flex-col items-center justify-center py-16 opacity-40">
            <span className="text-5xl mb-3">😔</span>
            <p className="text-sm">Nothing found for "{query}"</p>
          </div>
        )}

        {!loading && results.length > 0 && (
          <div className="space-y-2">
            {results.map((product) => (
              <Link
                key={product.id}
                to={`/product/${product.id}`}
                onClick={tgHapticLight}
                className="flex gap-3 p-3 rounded-2xl active:scale-[0.98] transition-transform"
                style={{
                  textDecoration: "none",
                  color: "var(--tg-theme-text-color, #000)",
                  background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                }}
              >
                <div
                  className="w-16 h-16 rounded-xl shrink-0 flex items-center justify-center text-2xl"
                  style={{ background: "var(--tg-theme-bg-color, #fff)" }}
                >
                  {product.currency_type === "XTR" ? "⭐" : product.currency_type === "CRYPTO" ? "💎" : "🛍️"}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-semibold text-sm leading-tight mb-1 truncate">{product.title}</p>
                  <p className="text-xs mb-2 line-clamp-1" style={{ color: "var(--tg-theme-hint-color, #999)" }}>
                    {product.description}
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
