import { useEffect } from "react";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import { TonConnectUIProvider } from "@tonconnect/ui-react";
import { useAppStore } from "./store/useAppStore";
import { AppLayout } from "./components/layout/AppLayout";
import { Catalog } from "./pages/Catalog";
import { SearchPage } from "./pages/Search";
import { DealsPage } from "./pages/Deals";
import { ProfilePage } from "./pages/Profile";
import { ProductDetails } from "./pages/ProductDetails";
import { Checkout } from "./pages/Checkout";
import { SellerDashboard } from "./pages/Seller";
import { ChatPage } from "./pages/Chat";
import { AdminPanel } from "./pages/AdminPanel";
import { NotificationsPage } from "./pages/Notifications";
import { tgExpand, tgReady, tgBindTheme, tgInitData } from "./lib/tg";

function AppInner() {
  const { setInitData } = useAppStore();

  const navigate = useNavigate();

  useEffect(() => {
    tgReady();
    tgExpand();
    tgBindTheme();
    setInitData(tgInitData());

    const tg = (window as any).Telegram?.WebApp;
    const startParam = tg?.initDataUnsafe?.start_param;
    if (startParam && startParam.startsWith("deal_")) {
      const dealId = startParam.replace("deal_", "");
      navigate(`/checkout/${dealId}`);
    }
  }, [setInitData, navigate]);

  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route path="/" element={<Catalog />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/deals" element={<DealsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
      {/* Full-screen routes (no bottom nav) */}
      <Route path="/product/:id" element={<ProductDetails />} />
      <Route path="/checkout/:dealId" element={<Checkout />} />
      <Route path="/seller" element={<SellerDashboard />} />
      <Route path="/chat/:dealId" element={<ChatPage />} />
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="/notifications" element={<NotificationsPage />} />
    </Routes>
  );
}

function App() {
  return (
    <TonConnectUIProvider manifestUrl="https://raw.githubusercontent.com/ton-community/tutorials/main/03-client/test/public/tonconnect-manifest.json">
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </TonConnectUIProvider>
  );
}

export default App;
