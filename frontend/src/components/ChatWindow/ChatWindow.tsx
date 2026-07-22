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
    <div className="mx-auto grid max-w-7xl gap-5 px-4 py-12 md:grid-cols-[280px_1fr] md:px-6 md:py-16 lg:px-8">
      {/* Contact List */}
      <div className="hidden overflow-hidden rounded-2xl border border-gray-200 bg-card dark:border-gray-800 md:block">
        <div className="border-b border-gray-200 p-5 dark:border-gray-800">
          <h3 className="font-display text-base font-bold text-foreground">💬 Messages</h3>
        </div>
        {contacts.map((c) => (
          <div
            key={c.name}
            className={cn(
              "flex items-center gap-3 border-b border-gray-200 px-5 py-3.5 transition-colors last:border-0 hover:bg-gray-50 dark:border-gray-800 dark:hover:bg-gray-800/50",
              c.active && "bg-gray-50 dark:bg-gray-800/50"
            )}
          >
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white">
              {c.avatar}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold text-foreground">{c.name}</div>
              <div className="truncate text-xs text-gray-600 dark:text-gray-400">{c.preview}</div>
            </div>
            {c.active && <div className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />}
          </div>
        ))}
      </div>

      {/* Chat Window */}
      <div className="flex h-130 flex-col rounded-2xl border border-gray-200 bg-card dark:border-gray-800">
        <div className="flex items-center gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-orange-600 text-xs font-bold text-white">
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
                    ? "rounded-bl-2xl rounded-br-sm bg-orange-600 text-white"
                    : "bg-gray-100 text-foreground dark:bg-gray-800"
                )}
              >
                {m.text}
              </div>
              <div className="mt-1 text-right text-xs text-gray-600 dark:text-gray-400">{m.time}</div>
            </div>
          ))}
          {typing && (
            <div className="max-w-[70%]">
              <div className="flex gap-1 rounded-2xl rounded-bl-sm bg-gray-100 px-4 py-3 dark:bg-gray-800">
                {[0, 1, 2].map((i) => (
                  <span
                    key={i}
                    className="block h-2 w-2 animate-pulse rounded-full bg-gray-500"
                    style={{ animationDelay: `${i * 0.15}s` }}
                  />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex gap-2.5 border-t border-gray-200 p-4 dark:border-gray-800">
          <Input
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage()}
          />
          <Button className="h-11 w-11 shrink-0 rounded-xl bg-orange-600 text-white hover:bg-orange-700" size="icon" onClick={sendMessage}>
            <Send className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
