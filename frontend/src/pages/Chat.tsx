import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Send, Package } from "lucide-react";
import { marketplaceApi, type ChatMessage, type DealDetails } from "../api/client";
import { tgHapticLight } from "../lib/tg";

export function ChatPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [deal, setDeal] = useState<DealDetails | null>(null);
  const [inputText, setInputText] = useState("");
  const [loading, setLoading] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pollInterval = useRef<number | null>(null);

  const myId = (window as any).Telegram?.WebApp?.initDataUnsafe?.user?.id || 0;

  useEffect(() => {
    if (!dealId) return;

    async function load() {
      try {
        const [dealData, msgData] = await Promise.all([
          marketplaceApi.getDeal(dealId!),
          marketplaceApi.getMessages(dealId!)
        ]);
        setDeal(dealData);
        setMessages(msgData);
      } catch (err) {
        console.error("Failed to load chat", err);
      } finally {
        setLoading(false);
      }
    }

    load();

    // Polling for new messages
    pollInterval.current = window.setInterval(async () => {
      try {
        const msgData = await marketplaceApi.getMessages(dealId!);
        setMessages(msgData);
      } catch (err) {
        console.error("Poll error", err);
      }
    }, 3000);

    return () => {
      if (pollInterval.current) clearInterval(pollInterval.current);
    };
  }, [dealId]);

  useEffect(() => {
    // Scroll to bottom on new messages
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!inputText.trim() || !dealId) return;
    const text = inputText;
    setInputText("");
    tgHapticLight();
    
    try {
      await marketplaceApi.sendMessage(dealId, text);
      const updated = await marketplaceApi.getMessages(dealId);
      setMessages(updated);
    } catch {
      alert("Failed to send message");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-zinc-950" style={{ background: "var(--tg-theme-bg-color, #fff)" }}>
      {/* Header */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-black/5" style={{ borderColor: "rgba(0,0,0,0.05)" }}>
        <button 
          onClick={() => navigate(-1)}
          className="p-1 -ml-1 rounded-full active:bg-black/5 transition-colors"
        >
          <ArrowLeft className="w-6 h-6" style={{ color: "var(--tg-theme-text-color, #000)" }} />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-sm font-bold truncate" style={{ color: "var(--tg-theme-text-color, #000)" }}>
            Deal Chat
          </h1>
          <p className="text-[10px] uppercase font-bold tracking-wider opacity-50" style={{ color: "var(--tg-theme-hint-color, #999)" }}>
            ID: {dealId?.slice(0, 8).toUpperCase()}
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/5">
            <Package className="w-3.5 h-3.5 opacity-50" />
            <span className="text-xs font-bold">{deal?.amount} {deal?.currency_type}</span>
        </div>
      </div>

      {/* Messages */}
      <div 
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-3"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full opacity-30 py-20">
            <div className="w-16 h-16 rounded-full bg-black/5 flex items-center justify-center mb-3">
              <Send className="w-8 h-8 -rotate-12" />
            </div>
            <p className="text-sm font-medium">Start the conversation</p>
          </div>
        ) : (
          messages.map((m) => {
            const isMe = m.sender_id === myId;
            return (
              <div 
                key={m.id} 
                className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}
              >
                <div 
                  className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm ${
                    isMe 
                      ? 'bg-blue-500 text-white rounded-tr-none' 
                      : 'bg-black/5 text-black dark:text-white rounded-tl-none'
                  }`}
                  style={isMe ? { 
                    background: "var(--tg-theme-button-color, #5288c1)",
                    color: "var(--tg-theme-button-text-color, #fff)"
                  } : {
                    background: "var(--tg-theme-secondary-bg-color, #f0f0f0)",
                    color: "var(--tg-theme-text-color, #000)"
                  }}
                >
                  <p className="leading-relaxed">{m.text}</p>
                  <p className="text-[9px] mt-1 opacity-50 text-right">
                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Input */}
      <div className="p-4 pt-2 border-t border-black/5" style={{ borderColor: "rgba(0,0,0,0.05)" }}>
        <div className="flex items-end gap-2 bg-black/5 p-1 rounded-2xl" style={{ background: "var(--tg-theme-secondary-bg-color, #f0f0f0)" }}>
          <textarea
            rows={1}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                }
            }}
            placeholder="Write a message..."
            className="flex-1 bg-transparent border-none outline-none p-3 text-sm resize-none"
            style={{ color: "var(--tg-theme-text-color, #000)" }}
          />
          <button 
            onClick={handleSend}
            disabled={!inputText.trim()}
            className="p-3 rounded-xl bg-blue-500 text-white disabled:opacity-30 transition-all active:scale-95"
            style={{ 
              background: "var(--tg-theme-button-color, #5288c1)",
              color: "var(--tg-theme-button-text-color, #fff)"
            }}
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
        <div className="h-safe-area-bottom"></div>
      </div>
    </div>
  );
}
