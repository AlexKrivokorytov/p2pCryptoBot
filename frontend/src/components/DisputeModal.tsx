import { useState } from "react";
import { tgHapticLight } from "../lib/tg";
import { marketplaceApi } from "../api/client";

interface DisputeModalProps {
  dealId: string;
  onClose: () => void;
  onSuccess: () => void;
}

export function DisputeModal({ dealId, onClose, onSuccess }: DisputeModalProps) {
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (reason.length < 20) {
      setError("Please describe the issue in at least 20 characters.");
      return;
    }

    setIsSubmitting(true);
    setError("");

    try {
      await marketplaceApi.openDispute(dealId, reason);
      tgHapticLight();
      onSuccess();
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to open dispute.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div
        className="w-full max-w-sm rounded-2xl p-5 shadow-lg"
        style={{ background: "var(--tg-theme-bg-color, #fff)", color: "var(--tg-theme-text-color, #000)" }}
      >
        <h3 className="text-lg font-bold mb-2">Open a Dispute</h3>

        <div
          className="p-3 rounded-xl text-sm mb-4"
          style={{ background: "rgba(244,67,54,0.1)", color: "#b71c1c" }}
        >
          <p className="font-semibold mb-1">⚠️ Important</p>
          <p>Disputes are reviewed manually by administrators. Funds will remain locked in escrow until the dispute is resolved.</p>
        </div>

        <textarea
          className="w-full rounded-xl p-3 text-sm mb-2"
          style={{
            background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
            color: "var(--tg-theme-text-color, #000)",
            border: "none",
            outline: "none",
            resize: "none"
          }}
          rows={4}
          placeholder="Please describe the issue in detail (min. 20 characters)..."
          value={reason}
          onChange={(e) => {
            setReason(e.target.value);
            if (error) setError("");
          }}
        />

        <div className="text-xs text-right mb-4" style={{ color: reason.length < 20 ? "#b71c1c" : "var(--tg-theme-hint-color, #999)" }}>
          {reason.length}/500
        </div>

        {error && (
          <p className="text-xs text-red-500 mb-4 text-center font-medium">{error}</p>
        )}

        <div className="flex gap-2">
          <button
            onClick={() => {
              tgHapticLight();
              onClose();
            }}
            className="flex-1 py-3 rounded-xl font-bold text-sm transition-opacity"
            style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)", color: "var(--tg-theme-text-color, #000)" }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSubmitting || reason.length < 20}
            className="flex-1 py-3 rounded-xl font-bold text-sm opacity-100 disabled:opacity-50 transition-opacity"
            style={{ background: "var(--tg-theme-button-color, #5288c1)", color: "#fff" }}
          >
            {isSubmitting ? "Submitting..." : "Submit"}
          </button>
        </div>
      </div>
    </div>
  );
}
