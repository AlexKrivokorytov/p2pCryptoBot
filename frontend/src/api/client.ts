import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Inject Telegram initData into every request automatically
apiClient.interceptors.request.use((config) => {
  const initData = (window as any).Telegram?.WebApp?.initData;
  if (initData) {
    config.headers.Authorization = `tma ${initData}`;
  }
  return config;
});

// ─── Types ───────────────────────────────────────────────────────────────────

export type CurrencyType = "XTR" | "FIAT" | "CRYPTO";
export type DealStatus = "created" | "paid" | "delivered" | "completed" | "dispute" | "cancelled";
export type DealRole = "buyer" | "seller";

export interface Product {
  id: string;
  seller_id: number;
  title: string;
  description?: string;
  price: number;
  currency_type: CurrencyType;
  fiat_currency?: string;
  crypto_asset?: string;
  crypto_chain?: string;
  is_digital: boolean;
  category?: string;
  is_active?: boolean;
  is_promoted?: boolean;
  image_urls?: string[];
  seller_rating?: number;
  seller_reviews_count?: number;
  is_verified_seller?: boolean;
}

export interface Deal {
  id: string;
  status: DealStatus;
  amount: number;
  currency_type: CurrencyType;
  product_title: string;
  role: DealRole;
  created_at?: string;
  dispute_reason?: string;
  dispute_opened_at?: string;
  dispute_resolution?: string;
}

export interface DealDetails {
  id: string;
  status: string;
  amount: number;
  currency_type: string;
  payment_method: string;
  payment_account: string;
  payment_name: string;
}

export interface CreateProductBody {
  title: string;
  description?: string;
  price: number;
  currency_type: CurrencyType;
  fiat_currency?: string;
  crypto_asset?: string;
  is_digital?: boolean;
  category?: string;
}

export interface UpdateProductBody {
  title?: string;
  description?: string;
  price?: number;
  is_active?: boolean;
  category?: string;
}

export interface ChatMessage {
  id: string;
  sender_id: number;
  text: string;
  created_at: string;
}

// ─── API Methods ─────────────────────────────────────────────────────────────

export const marketplaceApi = {
  // ── Products (public) ──────────────────────────────────────────────────
  getProducts: async (params?: {
    q?: string;
    category?: string;
    sort?: string;
    currency_type?: string;
  }) => {
    const res = await apiClient.get<Product[]>("/api/products", { params });
    return res.data;
  },

  getProduct: async (id: string) => {
    const res = await apiClient.get<Product>(`/api/products/${id}`);
    return res.data;
  },

  // ── Products (seller) ─────────────────────────────────────────────────
  createProduct: async (body: CreateProductBody) => {
    const res = await apiClient.post<Product>("/api/products", body);
    return res.data;
  },

  updateProduct: async (id: string, body: UpdateProductBody) => {
    const res = await apiClient.put(`/api/products/${id}`, body);
    return res.data;
  },

  deleteProduct: async (id: string) => {
    await apiClient.delete(`/api/products/${id}`);
  },

  createBoostInvoice: async (productId: string): Promise<{ invoice_url: string }> => {
    const res = await apiClient.post(`/api/products/${productId}/boost/invoice`);
    return res.data;
  },

  confirmBoost: async (productId: string) => {
    const res = await apiClient.post(`/api/products/${productId}/boost/confirm`);
    return res.data;
  },

  getSellerAnalytics: async () => {
    const res = await apiClient.get(`/api/seller/analytics`);
    return res.data;
  },

  getNotifications: async () => {
    const res = await apiClient.get(`/api/notifications`);
    return res.data;
  },

  markNotificationRead: async (id: string) => {
    const res = await apiClient.post(`/api/notifications/${id}/read`);
    return res.data;
  },

  uploadProductImages: async (id: string, files: File[]) => {
    const formData = new FormData();
    files.forEach(f => formData.append("files", f));
    const res = await apiClient.post<Product>(`/api/products/${id}/images`, formData, {
      headers: { "Content-Type": "multipart/form-data" }
    });
    return res.data;
  },

  deleteProduct: async (id: string) => {
    await apiClient.delete(`/api/products/${id}`);
  },

  getMyProducts: async () => {
    const res = await apiClient.get<Product[]>("/api/seller/products");
    return res.data;
  },

  // ── Stars Payment ─────────────────────────────────────────────────────
  createStarsInvoice: async (productId: string, promoCode?: string) => {
    const res = await apiClient.post<{ invoice_url: string }>(`/api/products/${productId}/invoice`, { promo_code: promoCode });
    return res.data;
  },

  confirmStarsDeal: async (productId: string, chargeId: string) => {
    const res = await apiClient.post("/api/deals/stars-confirm", {
      product_id: productId,
      telegram_payment_charge_id: chargeId,
    });
    return res.data;
  },

  // ── Deals ─────────────────────────────────────────────────────────────
  createDeal: async (productId: string, promoCode?: string) => {
    const res = await apiClient.post<{ id: string; status: string; amount: number }>(
      "/api/deals",
      { product_id: productId, promo_code: promoCode }
    );return res.data;
  },

  getMyDeals: async () => {
    const res = await apiClient.get<Deal[]>("/api/deals");
    return res.data;
  },

  getDeal: async (dealId: string) => {
    const res = await apiClient.get<DealDetails>(`/api/deals/${dealId}`);
    return res.data;
  },

  markDealPaid: async (dealId: string) => {
    await apiClient.post(`/api/deals/${dealId}/pay`);
  },

  deliverDeal: async (dealId: string) => {
    await apiClient.post(`/api/deals/${dealId}/deliver`);
  },

  completeDeal: async (dealId: string) => {
    await apiClient.post(`/api/deals/${dealId}/complete`);
  },

  openDispute: async (dealId: string, reason: string) => {
    const res = await apiClient.post(`/api/deals/${dealId}/dispute`, { reason });
    return res.data;
  },

  // ── Chat ─────────────────────────────────────────────────────────────
  getMessages: async (dealId: string) => {
    const res = await apiClient.get<ChatMessage[]>(`/api/deals/${dealId}/messages`);
    return res.data;
  },

  sendMessage: async (dealId: string, text: string) => {
    await apiClient.post(`/api/deals/${dealId}/messages`, { text });
  },

  createReview: async (dealId: string, rating: number, comment?: string) => {
    await apiClient.post(`/api/deals/${dealId}/review`, { rating, comment });
  },

  // ── Admin ─────────────────────────────────────────────────────────────
  getAdminDisputes: async () => {
    const res = await apiClient.get<any[]>("/api/admin/marketplace-disputes");
    return res.data;
  },

  resolveAdminDispute: async (dealId: string, resolution: "buyer" | "seller", comment: string) => {
    await apiClient.post(`/api/admin/marketplace-disputes/${dealId}/resolve`, {
      resolution,
      comment
    });
  },

  // ── Promo Codes ────────────────────────────────────────────────────────
  getPromoCodes: async () => {
    const res = await apiClient.get<PromoCode[]>("/api/promo-codes");
    return res.data;
  },

  createPromoCode: async (code: string, discount_type: "percentage" | "fixed", discount_value: number, max_uses?: number) => {
    const res = await apiClient.post<PromoCode>("/api/promo-codes", {
      code, discount_type, discount_value, max_uses
    });
    return res.data;
  },

  validatePromoCode: async (code: string, product_id: string) => {
    const res = await apiClient.post<{ valid: boolean; discount_type: string; discount_value: number }>("/api/promo-codes/validate", {
      code, product_id
    });
    return res.data;
  },
};
