import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Pencil, Trash2, ToggleLeft, ToggleRight, ChevronLeft, Star } from "lucide-react";
import type { Product, CreateProductBody, CurrencyType, PromoCode } from "../api/client";
import { marketplaceApi } from "../api/client";
import { tgHapticLight, tgHapticSuccess, tgHapticError, tgShowConfirm, tgShowAlert } from "../lib/tg";

// ─── Promo Codes Tab ─────────────────────────────────────────────────────────

function PromoCodesTab() {
  const [promos, setPromos] = useState<PromoCode[]>([]);
  const [loading, setLoading] = useState(true);

  const [showAdd, setShowAdd] = useState(false);
  const [code, setCode] = useState("");
  const [type, setType] = useState<"percentage" | "fixed">("percentage");
  const [value, setValue] = useState(0);
  const [maxUses, setMaxUses] = useState<number | "">("");

  useEffect(() => {
    marketplaceApi.getPromoCodes()
      .then(setPromos)
      .finally(() => setLoading(false));
  }, []);

  async function handleAdd() {
    if (!code.trim() || value <= 0) {
      await tgShowAlert("Please enter a valid code and value");
      return;
    }
    try {
      const res = await marketplaceApi.createPromoCode(
        code.trim(),
        type,
        value,
        maxUses === "" ? undefined : maxUses
      );
      setPromos([...promos, res]);
      setShowAdd(false);
      setCode("");
      setValue(0);
      setMaxUses("");
      tgHapticSuccess();
    } catch (err: any) {
      tgHapticError();
      await tgShowAlert(err?.response?.data?.detail || "Failed to create promo code");
    }
  }

  if (loading) return <div className="p-4 opacity-50">Loading...</div>;

  return (
    <div className="flex flex-col h-full">
      <div className="flex justify-between items-center px-4 py-2">
        <h2 className="font-bold text-lg">My Promo Codes</h2>
        <button
          onClick={() => { tgHapticLight(); setShowAdd(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-sm font-semibold"
          style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff" }}
        >
          <Plus className="w-4 h-4" /> Add
        </button>
      </div>

      {showAdd && (
        <div className="p-4 mx-4 mb-4 rounded-2xl space-y-3" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
          <input
            placeholder="Code (e.g. SUMMER20)"
            value={code}
            onChange={e => setCode(e.target.value.toUpperCase())}
            className="w-full px-3 py-2 rounded-lg text-sm bg-white text-black"
          />
          <div className="flex gap-2">
            <select
              value={type}
              onChange={e => setType(e.target.value as any)}
              className="px-3 py-2 rounded-lg text-sm bg-white text-black"
            >
              <option value="percentage">% Percentage</option>
              <option value="fixed">Fixed amount</option>
            </select>
            <input
              type="number"
              placeholder="Value"
              value={value || ""}
              onChange={e => setValue(Number(e.target.value))}
              className="flex-1 px-3 py-2 rounded-lg text-sm bg-white text-black"
            />
          </div>
          <input
            type="number"
            placeholder="Max uses (optional)"
            value={maxUses}
            onChange={e => setMaxUses(e.target.value ? Number(e.target.value) : "")}
            className="w-full px-3 py-2 rounded-lg text-sm bg-white text-black"
          />
          <div className="flex gap-2">
            <button onClick={() => setShowAdd(false)} className="flex-1 py-2 rounded-lg text-sm opacity-70 border">Cancel</button>
            <button onClick={handleAdd} className="flex-1 py-2 rounded-lg text-sm font-semibold" style={{ background: "var(--tg-theme-button-color)", color: "#fff" }}>Save</button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
        {promos.length === 0 ? (
          <p className="text-center text-xs opacity-50 py-8">No promo codes active</p>
        ) : promos.map(p => (
          <div key={p.id} className="p-3 rounded-xl flex items-center justify-between" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
            <div>
              <p className="font-bold">{p.code}</p>
              <p className="text-xs opacity-60">Uses: {p.current_uses} / {p.max_uses || '∞'}</p>
            </div>
            <div className="font-bold text-sm" style={{ color: "var(--tg-theme-button-color)" }}>
              {p.discount_type === "percentage" ? `${p.discount_value}%` : `-${p.discount_value}`}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Category & Currency options ──────────────────────────────────────────────

const CATEGORIES = ["mentorship", "design", "social", "education", "digital", "other"];
const CURRENCY_OPTS: { value: CurrencyType; label: string; hint: string }[] = [
  { value: "XTR",   label: "⭐ Stars",  hint: "Telegram Stars — instant, no fees" },
  { value: "FIAT",  label: "💵 Fiat",   hint: "Bank transfer via escrow" },
  { value: "CRYPTO",label: "💎 Crypto", hint: "TON / on-chain payment" },
];

// ─── Empty form ───────────────────────────────────────────────────────────────

const emptyForm = (): CreateProductBody => ({
  title: "",
  description: "",
  price: 0,
  currency_type: "XTR",
  is_digital: true,
  category: "digital",
});

// ─── ProductForm modal ────────────────────────────────────────────────────────

interface FormProps {
  initial?: Partial<CreateProductBody> & { id?: string };
  onSave: (data: CreateProductBody, id?: string) => Promise<string | undefined>;
  onClose: () => void;
}

function ProductForm({ initial, onSave, onClose }: FormProps) {
  const [form, setForm] = useState<CreateProductBody>({ ...emptyForm(), ...initial });
  const [saving, setSaving] = useState(false);
  const isEdit = Boolean(initial?.id);

  const [images, setImages] = useState<File[]>([]);

  function set<K extends keyof CreateProductBody>(key: K, value: CreateProductBody[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    if (!form.title.trim()) {
      await tgShowAlert("Please enter a title.");
      return;
    }
    if (form.price <= 0) {
      await tgShowAlert("Price must be greater than 0.");
      return;
    }
    setSaving(true);
    try {
      const savedId = await onSave(form, initial?.id);

      if (savedId && images.length > 0) {
        await marketplaceApi.uploadProductImages(savedId, images);
      }

      tgHapticSuccess();
      onClose();
    } catch {
      tgHapticError();
      await tgShowAlert("Failed to save product or images. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  const selectedCurrency = CURRENCY_OPTS.find((c) => c.value === form.currency_type)!;

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col"
      style={{ background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}
    >
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 border-b"
        style={{ borderColor: "rgba(128,128,128,0.15)" }}
      >
        <button onClick={onClose} className="p-1 rounded-lg" style={{ background: "none", border: "none", cursor: "pointer" }}>
          <ChevronLeft className="w-6 h-6" />
        </button>
        <h2 className="font-bold text-lg flex-1">{isEdit ? "Edit Product" : "New Listing"}</h2>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-4 py-1.5 rounded-xl text-sm font-semibold"
          style={{
            background: saving ? "rgba(128,128,128,0.2)" : "var(--tg-theme-button-color, #5288c1)",
            color: saving ? "var(--tg-theme-hint-color)" : "var(--tg-theme-button-text-color, #fff)",
            border: "none",
            cursor: saving ? "not-allowed" : "pointer",
          }}
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      {/* Scrollable form body */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {/* Title */}
        <div>
          <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Title *</label>
          <input
            value={form.title}
            onChange={(e) => set("title", e.target.value)}
            maxLength={80}
            placeholder="e.g. Figma Design Kit"
            className="w-full px-4 py-3 rounded-xl text-sm outline-none"
            style={{
              background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
              color: "var(--tg-theme-text-color, #000)",
              border: "none",
            }}
          />
        </div>

        {/* Images */}
        <div>
          <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Images (up to 5)</label>
          <input
            type="file"
            multiple
            accept="image/*"
            onChange={(e) => {
              if (e.target.files) {
                const selected = Array.from(e.target.files).slice(0, 5);
                setImages(selected);
              }
            }}
            className="w-full px-4 py-3 rounded-xl text-sm outline-none"
            style={{
              background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
              color: "var(--tg-theme-text-color, #000)",
              border: "none",
            }}
          />
          {images.length > 0 && (
            <p className="text-xs mt-1.5 opacity-50">{images.length} file(s) selected.</p>
          )}
        </div>

        {/* Description */}
        <div>
          <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Description</label>
          <textarea
            value={form.description ?? ""}
            onChange={(e) => set("description", e.target.value)}
            rows={4}
            placeholder="Describe what the buyer will receive…"
            className="w-full px-4 py-3 rounded-xl text-sm outline-none resize-none"
            style={{
              background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
              color: "var(--tg-theme-text-color, #000)",
              border: "none",
            }}
          />
        </div>

        {/* Currency */}
        <div>
          <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Payment Type *</label>
          <div className="grid grid-cols-3 gap-2">
            {CURRENCY_OPTS.map((opt) => {
              const active = form.currency_type === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => { tgHapticLight(); set("currency_type", opt.value); }}
                  className="flex flex-col items-center py-3 rounded-xl text-sm font-semibold transition-all"
                  style={{
                    background: active ? "var(--tg-theme-button-color, #5288c1)" : "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                    color: active ? "var(--tg-theme-button-text-color, #fff)" : "var(--tg-theme-text-color, #000)",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  <span className="text-lg mb-0.5">{opt.label.split(" ")[0]}</span>
                  <span className="text-xs">{opt.label.split(" ")[1]}</span>
                </button>
              );
            })}
          </div>
          <p className="text-xs mt-1.5 opacity-50">{selectedCurrency.hint}</p>
        </div>

        {/* Price */}
        <div>
          <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">
            Price *&nbsp;
            <span className="normal-case font-normal">
              {form.currency_type === "XTR" ? "(Stars)" : form.currency_type === "FIAT" ? "(USD)" : "(TON)"}
            </span>
          </label>
          <div
            className="flex items-center rounded-xl overflow-hidden"
            style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}
          >
            <span className="px-4 text-lg shrink-0">
              {form.currency_type === "XTR" ? <Star className="w-4 h-4 fill-yellow-400 stroke-yellow-500" /> : form.currency_type === "FIAT" ? "$" : "◈"}
            </span>
            <input
              type="number"
              min={0}
              step={form.currency_type === "CRYPTO" ? 0.01 : 1}
              value={form.price || ""}
              onChange={(e) => set("price", parseFloat(e.target.value) || 0)}
              placeholder="0"
              className="flex-1 py-3 pr-4 text-sm outline-none bg-transparent"
              style={{ color: "var(--tg-theme-text-color, #000)", border: "none" }}
            />
          </div>
        </div>

        {/* Sub-field: fiat_currency */}
        {form.currency_type === "FIAT" && (
          <div>
            <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Fiat Currency</label>
            <select
              value={form.fiat_currency ?? "USD"}
              onChange={(e) => set("fiat_currency", e.target.value)}
              className="w-full px-4 py-3 rounded-xl text-sm outline-none"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", color: "var(--tg-theme-text-color, #000)", border: "none" }}
            >
              {["USD", "EUR", "RUB", "GBP", "USDT"].map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
        )}

        {/* Sub-field: crypto_asset */}
        {form.currency_type === "CRYPTO" && (
          <div>
            <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Crypto Asset</label>
            <select
              value={form.crypto_asset ?? "TON"}
              onChange={(e) => set("crypto_asset", e.target.value)}
              className="w-full px-4 py-3 rounded-xl text-sm outline-none"
              style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", color: "var(--tg-theme-text-color, #000)", border: "none" }}
            >
              {["TON", "USDT", "ETH", "BTC"].map((c) => <option key={c}>{c}</option>)}
            </select>
          </div>
        )}

        {/* Category */}
        <div>
          <label className="block text-xs font-bold mb-1.5 opacity-50 uppercase tracking-wider">Category</label>
          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((cat) => {
              const active = form.category === cat;
              return (
                <button
                  key={cat}
                  onClick={() => { tgHapticLight(); set("category", cat); }}
                  className="px-3 py-1.5 rounded-full text-xs font-medium capitalize"
                  style={{
                    background: active ? "var(--tg-theme-button-color, #5288c1)" : "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                    color: active ? "var(--tg-theme-button-text-color, #fff)" : "var(--tg-theme-text-color, #000)",
                    border: "none",
                    cursor: "pointer",
                  }}
                >
                  {cat}
                </button>
              );
            })}
          </div>
        </div>

        {/* Type toggle */}
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-sm font-semibold">Digital product</p>
            <p className="text-xs opacity-50">Delivered online (files, links, access)</p>
          </div>
          <button
            onClick={() => { tgHapticLight(); set("is_digital", !form.is_digital); }}
            style={{ background: "none", border: "none", cursor: "pointer" }}
          >
            {form.is_digital
              ? <ToggleRight className="w-8 h-8" style={{ color: "var(--tg-theme-button-color)" }} />
              : <ToggleLeft className="w-8 h-8 opacity-40" />}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main SellerPage ──────────────────────────────────────────────────────────

export function SellerDashboard() {
  const navigate = useNavigate();
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<any>(null);
  const [showForm, setShowForm] = useState(false);
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [activeTab, setActiveTab] = useState<"products" | "promos">("products");

  async function handleBoost(product: Product) {
    tgHapticLight();
    const ok = await tgShowConfirm(`Boost "${product.title}" for 24 hours? Cost: 50 Stars.`);
    if (!ok) return;
    try {
      const { invoice_url } = await marketplaceApi.createBoostInvoice(product.id);
      const WebApp = (window as any).Telegram?.WebApp;
      if (WebApp?.openInvoice) {
        WebApp.openInvoice(invoice_url, async (status: string) => {
          if (status === "paid") {
            await marketplaceApi.confirmBoost(product.id);
            tgHapticSuccess();
            await loadProducts();
            tgShowAlert("Product boosted successfully! 🚀");
          } else {
            tgHapticError();
            tgShowAlert("Payment was not completed.");
          }
        });
      } else {
        window.open(invoice_url, "_blank");
      }
    } catch (e: any) {
      tgHapticError();
      tgShowAlert(e.response?.data?.detail || "Failed to create boost invoice.");
    }
  }

  async function loadProducts() {
    setLoading(true);
    try {
      const [productsData, analyticsData] = await Promise.all([
        marketplaceApi.getMyProducts(),
        marketplaceApi.getSellerAnalytics()
      ]);
      setProducts(productsData);
      setAnalytics(analyticsData);
    } catch {
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadProducts(); }, []);

  async function handleSave(body: CreateProductBody, id?: string) {
    let savedId = id;
    if (id) {
      const res = await marketplaceApi.updateProduct(id, body);
      savedId = res.id;
    } else {
      const res = await marketplaceApi.createProduct(body);
      savedId = res.id;
    }
    await loadProducts();
    return savedId;
  }

  async function handleToggleActive(product: Product) {
    tgHapticLight();
    try {
      await marketplaceApi.updateProduct(product.id, { is_active: !product.is_active });
      await loadProducts();
    } catch {
      await tgShowAlert("Failed to update product.");
    }
  }

  async function handleDelete(product: Product) {
    const ok = await tgShowConfirm(`Delete "${product.title}"? This cannot be undone.`);
    if (!ok) return;
    try {
      await marketplaceApi.deleteProduct(product.id);
      tgHapticSuccess();
      await loadProducts();
    } catch {
      await tgShowAlert("Failed to delete product.");
    }
  }

  if (showForm || editProduct) {
    return (
      <ProductForm
        initial={editProduct ? { ...editProduct } : undefined}
        onSave={handleSave}
        onClose={() => { setShowForm(false); setEditProduct(null); }}
      />
    );
  }

  return (
    <div className="flex flex-col h-full" style={{ background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <button onClick={() => navigate("/profile")} style={{ background: "none", border: "none", cursor: "pointer", padding: 4 }}>
          <ChevronLeft className="w-6 h-6" />
        </button>
        <h1 className="text-xl font-bold flex-1">My Products</h1>
        <button
          onClick={() => { tgHapticLight(); setShowForm(true); }}
          className="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm font-semibold"
          style={{
            background: "var(--tg-theme-button-color, #5288c1)",
            color: "var(--tg-theme-button-text-color, #fff)",
            border: "none",
            cursor: "pointer",
          }}
        >
          <Plus className="w-4 h-4" />
          Add
        </button>
      </div>
      <div className="px-4 pt-4 pb-2">
        <h1 className="text-2xl font-bold mb-4">Seller Dashboard</h1>

        {/* Analytics Block */}
        {analytics && (
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="p-3 rounded-2xl flex flex-col" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
              <span className="text-xs opacity-60 font-semibold uppercase tracking-wider mb-1">Total Deals</span>
              <span className="text-xl font-bold">{analytics.successful_deals_count}</span>
            </div>
            <div className="p-3 rounded-2xl flex flex-col" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
              <span className="text-xs opacity-60 font-semibold uppercase tracking-wider mb-1">XTR Earned</span>
              <span className="text-xl font-bold text-yellow-500">⭐ {analytics.total_revenue.XTR}</span>
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex px-4 pb-2 border-b mb-3" style={{ borderColor: "rgba(128,128,128,0.15)" }}>
        <button
          onClick={() => setActiveTab("products")}
          className={`flex-1 pb-2 font-semibold text-sm ${activeTab === "products" ? "border-b-2" : "opacity-50"}`}
          style={{ borderColor: "var(--tg-theme-button-color, #5288c1)" }}
        >
          Products
        </button>
        <button
          onClick={() => setActiveTab("promos")}
          className={`flex-1 pb-2 font-semibold text-sm ${activeTab === "promos" ? "border-b-2" : "opacity-50"}`}
          style={{ borderColor: "var(--tg-theme-button-color, #5288c1)" }}
        >
          Promo Codes
        </button>
      </div>

      {activeTab === "promos" ? (
        <PromoCodesTab />
      ) : (
        <>
          {/* Stats bar */}
          <div className="flex gap-3 px-4 pb-3">
            {[
              { label: "Total", value: products.length },
              { label: "Active", value: products.filter((p) => p.is_active).length },
              { label: "Paused", value: products.filter((p) => !p.is_active).length },
            ].map((s) => (
              <div key={s.label} className="flex-1 py-2 rounded-xl text-center"
                style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
                <p className="font-bold text-lg">{s.value}</p>
                <p className="text-xs opacity-50">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Product list */}
          <div className="flex-1 overflow-y-auto px-4 pb-4">
            {loading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-20 rounded-2xl animate-pulse"
                    style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }} />
                ))}
              </div>
            ) : products.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16 opacity-40">
                <span className="text-5xl mb-3">🛍️</span>
                <p className="text-sm font-medium mb-1">No products yet</p>
                <p className="text-xs">Tap "+ Add" to create your first listing</p>
              </div>
            ) : (
              <div className="space-y-2">
                {products.map((product) => (
                  <div
                    key={product.id}
                    className="flex items-center gap-3 p-4 rounded-2xl"
                    style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}
                  >
                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <p className="font-semibold text-sm truncate">{product.title}</p>
                        {!product.is_active && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded-full shrink-0"
                            style={{ background: "rgba(158,158,158,0.2)", color: "var(--tg-theme-hint-color)" }}>
                            Paused
                          </span>
                        )}
                      </div>
                      <p className="text-xs font-bold" style={{ color: "var(--tg-theme-button-color, #5288c1)" }}>
                        {product.currency_type === "XTR" && `⭐ ${product.price}`}
                        {product.currency_type === "FIAT" && `$${product.price}`}
                        {product.currency_type === "CRYPTO" && `${product.price} ${product.crypto_asset}`}
                        <span className="font-normal opacity-50 ml-1">· {product.category}</span>
                      </p>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-1 shrink-0">
                      {/* Boost */}
                      {!product.is_promoted && (
                        <button
                          onClick={() => handleBoost(product)}
                          className="p-2 rounded-xl text-yellow-500 hover:bg-yellow-500/10 transition-colors"
                          style={{ background: "none", border: "none", cursor: "pointer" }}
                          title="Boost product (50 XTR for 24h)"
                        >
                          🚀
                        </button>
                      )}
                      {/* Toggle active */}
                      <button
                        onClick={() => handleToggleActive(product)}
                        className="p-2 rounded-xl"
                        style={{ background: "none", border: "none", cursor: "pointer" }}
                        title={product.is_active ? "Pause listing" : "Activate listing"}
                      >
                        {product.is_active
                          ? <ToggleRight className="w-5 h-5" style={{ color: "var(--tg-theme-button-color)" }} />
                          : <ToggleLeft className="w-5 h-5 opacity-40" />}
                      </button>
                      {/* Edit */}
                      <button
                        onClick={() => { tgHapticLight(); setEditProduct(product); }}
                        className="p-2 rounded-xl"
                        style={{ background: "none", border: "none", cursor: "pointer" }}
                      >
                        <Pencil className="w-4 h-4 opacity-60" />
                      </button>
                      {/* Delete */}
                      <button
                        onClick={() => handleDelete(product)}
                        className="p-2 rounded-xl"
                        style={{ background: "none", border: "none", cursor: "pointer" }}
                      >
                        <Trash2 className="w-4 h-4" style={{ color: "#ef4444" }} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
