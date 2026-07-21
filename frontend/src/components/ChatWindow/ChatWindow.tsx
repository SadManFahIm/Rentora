import { useState } from "react";
import { mockMessages } from "../../data/mockData";
import type { Message } from "../../types";
import "./ChatWindow.css";

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
    <div className="chat-section">
      {/* Contact List */}
      <div className="chat-list">
        <div className="chat-list-header"><h3>💬 Messages</h3></div>
        {contacts.map((c) => (
          <div key={c.name} className={`chat-contact ${c.active ? "active" : ""}`}>
            <div className="owner-avatar">{c.avatar}</div>
            <div className="chat-contact-info">
              <div className="chat-contact-name">{c.name}</div>
              <div className="chat-contact-preview">{c.preview}</div>
            </div>
            {c.active && <div className="online-dot" />}
          </div>
        ))}
      </div>

      {/* Chat Window */}
      <div className="chat-window">
        <div className="chat-window-header">
          <div className="owner-avatar">RH</div>
          <div>
            <div style={{ fontWeight: 700, fontSize: "0.9rem" }}>Rahim Hossain</div>
            <div className="online-status">● Online</div>
          </div>
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button className="icon-btn" title="Attach file">📎</button>
            <button className="icon-btn" title="Voice call">📞</button>
          </div>
        </div>

        <div className="chat-messages">
          {messages.map((m) => (
            <div key={m.id} className={`message ${m.mine ? "mine" : ""}`}>
              <div className="message-bubble">{m.text}</div>
              <div className="message-time">{m.time}</div>
            </div>
          ))}
          {typing && (
            <div className="message">
              <div className="message-bubble typing-bubble">
                {[0, 1, 2].map((i) => (
                  <span key={i} className="typing-dot" style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="chat-input-wrap">
          <input
            className="chat-input"
            placeholder="Type a message..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && sendMessage()}
          />
          <button className="send-btn" onClick={sendMessage}>➤</button>
        </div>
      </div>
    </div>
  );
}
