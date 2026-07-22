import { useState } from "react";
import { Paperclip, Phone, Send } from "lucide-react";
import { mockMessages } from "../../data/mockData";
import type { Message } from "../../types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { cn } from "../../lib/utils";

interface Contact {
  name: string;
  avatar: string;
  preview: string;
  active: boolean;
}

const contacts: Contact[] = [
  { name: "Rahim Hossain", avatar: "RH", preview: "Saturday 11AM works...", active: true },
  { name: "Nadia Islam", avatar: "NI", preview: "The room is available...", active: false },
  { name: "Arif Khan", avatar: "AK", preview: "Please visit anytime...", active: false },
];

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>(mockMessages);
  const [input, setInput] = useState("");
  const [typing, setTyping] = useState(false);

  const sendMessage = () => {
    if (!input.trim()) return;
    setMessages((m) => [...m, { id: Date.now(), from: "Me", avatar: "ME", text: input, time: "Now", mine: true }]);
    setInput("");
    setTyping(true);
    setTimeout(() => {
      setTyping(false);
      setMessages((m) => [...m, { id: Date.now() + 1, from: "Rahim Hossain", avatar: "RH", text: "Thanks for your message! I'll get back to you shortly.", time: "Now", mine: false }]);
    }, 1800);
  };

  return (
    <div className="mx-auto grid max-w-300 gap-5 px-4 py-8 sm:px-8 md:grid-cols-[280px_1fr]">
      {/* Contact List */}
      <div className="hidden overflow-hidden rounded-2xl border border-border bg-card md:block">
        <div className="border-b border-border p-5">
          <h3 className="font-display text-base font-bold text-foreground">💬 Messages</h3>
        </div>
        {contacts.map((c) => (
          <div
            key={c.name}
            className={cn(
              "flex items-center gap-3 border-b border-border px-5 py-3.5 transition-colors last:border-0 hover:bg-muted",
              c.active && "bg-muted"
            )}
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-linear-to-br from-brand to-brand-dark text-xs font-bold text-white">
              {c.avatar}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-foreground">{c.name}</div>
              <div className="truncate text-xs text-muted-foreground">{c.preview}</div>
            </div>
            {c.active && <div className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />}
          </div>
        ))}
      </div>

      {/* Chat Window */}
      <div className="flex h-130 flex-col rounded-2xl border border-border bg-card">
        <div className="flex items-center gap-3 border-b border-border px-5 py-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-linear-to-br from-brand to-brand-dark text-xs font-bold text-white">
            RH
          </div>
          <div>
            <div className="text-sm font-bold text-foreground">Rahim Hossain</div>
            <div className="text-xs text-emerald-500">● Online</div>
          </div>
          <div className="ml-auto flex gap-2">
            <Button variant="outline" size="icon" className="rounded-xl" title="Attach file">
              <Paperclip className="size-4" />
            </Button>
            <Button variant="outline" size="icon" className="rounded-xl" title="Voice call">
              <Phone className="size-4" />
            </Button>
          </div>
        </div>

        <div className="flex flex-1 flex-col gap-3 overflow-y-auto p-5">
          {messages.map((m) => (
            <div key={m.id} className={cn("max-w-[70%]", m.mine && "self-end")}>
              <div
                className={cn(
                  "rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm leading-relaxed",
                  m.mine
                    ? "rounded-bl-2xl rounded-br-sm bg-brand text-white"
                    : "bg-muted text-foreground"
                )}
              >
                {m.text}
              </div>
              <div className="mt-1 text-right text-xs text-muted-foreground">{m.time}</div>
            </div>
          ))}
          {typing && (
            <div className="max-w-[70%]">
              <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-muted px-4 py-3">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="block h-2 w-2 animate-pulse rounded-full bg-muted-foreground"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2.5 border-t border-border p-4">
          <Input
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          />
          <Button variant="brand" size="icon" className="h-11 w-11 shrink-0 rounded-xl" onClick={sendMessage}>
            <Send className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
