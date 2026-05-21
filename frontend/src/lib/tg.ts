/**
 * Thin wrapper around window.Telegram.WebApp for safe, type-checked usage.
 * Falls back gracefully when running outside Telegram (e.g. browser dev).
 */

const tg = (): any => (window as any).Telegram?.WebApp;

/** Expand the Mini App to full-screen height. */
export function tgExpand(): void {
  tg()?.expand();
}

/** Signal to Telegram that the Mini App is ready to display. */
export function tgReady(): void {
  tg()?.ready();
}

/** Trigger light haptic feedback on element tap. */
export function tgHapticLight(): void {
  tg()?.HapticFeedback?.impactOccurred("light");
}

/** Trigger success haptic notification. */
export function tgHapticSuccess(): void {
  tg()?.HapticFeedback?.notificationOccurred("success");
}

/** Trigger error haptic notification. */
export function tgHapticError(): void {
  tg()?.HapticFeedback?.notificationOccurred("error");
}

/** Show and configure the Main Button. */
export function tgMainButtonShow(params: {
  text: string;
  color?: string;
  textColor?: string;
}): void {
  const btn = tg()?.MainButton;
  if (!btn) return;
  btn.setText(params.text);
  if (params.color) btn.color = params.color;
  if (params.textColor) btn.textColor = params.textColor;
  btn.show();
}

/** Hide the Main Button. */
export function tgMainButtonHide(): void {
  tg()?.MainButton?.hide();
}

/** Show loading spinner on the Main Button. */
export function tgMainButtonShowProgress(): void {
  tg()?.MainButton?.showProgress();
}

/** Hide loading spinner on the Main Button. */
export function tgMainButtonHideProgress(): void {
  tg()?.MainButton?.hideProgress();
}

/** Register a click handler on the Main Button. Returns an unsubscribe fn. */
export function tgMainButtonOnClick(handler: () => void): () => void {
  const btn = tg()?.MainButton;
  if (!btn) return () => {};
  btn.onClick(handler);
  return () => btn.offClick(handler);
}

/** Show the Back Button. Returns an unsubscribe fn. */
export function tgBackButtonShow(handler: () => void): () => void {
  const btn = tg()?.BackButton;
  if (!btn) return () => {};
  btn.show();
  btn.onClick(handler);
  return () => {
    btn.offClick(handler);
    btn.hide();
  };
}

/** Get initData string from Telegram WebApp. */
export function tgInitData(): string {
  return tg()?.initData ?? "";
}

/**
 * Open a Telegram Stars invoice link.
 * Calls window.Telegram.WebApp.openInvoice and resolves with the final status.
 *
 * @param url - The invoice link returned by createInvoiceLink Bot API method.
 * @returns Promise resolving to "paid" | "cancelled" | "failed" | "pending"
 */
export function tgOpenInvoice(url: string): Promise<string> {
  return new Promise((resolve) => {
    const webApp = tg();
    if (!webApp?.openInvoice) {
      // Dev fallback: simulate paid after 1s
      console.warn("[tg] openInvoice not available — simulating 'paid'");
      setTimeout(() => resolve("paid"), 1000);
      return;
    }
    webApp.openInvoice(url, (status: string) => resolve(status));
  });
}

/** Show a native Telegram popup (confirmation dialog). */
export function tgShowConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    const webApp = tg();
    if (!webApp?.showConfirm) {
      resolve(window.confirm(message));
      return;
    }
    webApp.showConfirm(message, (ok: boolean) => resolve(ok));
  });
}

/** Show a native Telegram popup alert. */
export function tgShowAlert(message: string): Promise<void> {
  return new Promise((resolve) => {
    const webApp = tg();
    if (!webApp?.showAlert) {
      alert(message);
      resolve();
      return;
    }
    webApp.showAlert(message, () => resolve());
  });
}

/** Bind Telegram CSS color vars to the document. */
export function tgBindTheme(): void {
  const themeParams = tg()?.themeParams;
  if (!themeParams) return;
  const root = document.documentElement;
  const map: Record<string, string> = {
    "--tg-theme-bg-color": themeParams.bg_color,
    "--tg-theme-text-color": themeParams.text_color,
    "--tg-theme-hint-color": themeParams.hint_color,
    "--tg-theme-link-color": themeParams.link_color,
    "--tg-theme-button-color": themeParams.button_color,
    "--tg-theme-button-text-color": themeParams.button_text_color,
    "--tg-theme-secondary-bg-color": themeParams.secondary_bg_color,
  };
  for (const [key, val] of Object.entries(map)) {
    if (val) root.style.setProperty(key, val);
  }
}
