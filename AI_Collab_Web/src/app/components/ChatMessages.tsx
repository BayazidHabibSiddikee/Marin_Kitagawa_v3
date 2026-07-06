import { useEffect, useRef } from 'react';

export interface Message {
  id: string;
  role: 'ai' | 'user';
  content: string;
  isTyping?: boolean;
}

interface ChatMessagesProps {
  messages: Message[];
}

function renderBubbleContent(content: string) {
  const parts = content.split(/(\*\*.*?\*\*|`[^`]+`|\*.*?\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return <span key={i}>{part}</span>;
  });
}

export function ChatMessages({ messages }: ChatMessagesProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div className="marin-messages">
      {messages.map(msg => (
        <div key={msg.id} className={`marin-msg ${msg.role}`}>
          <div className={`marin-avatar ${msg.role}`}>
            {msg.role === 'ai' ? 'M' : '◉'}
          </div>
          <div className="marin-bubble">
            {msg.isTyping ? (
              <div className="marin-typing-dots">
                <span />
                <span />
                <span />
              </div>
            ) : (
              <span className="bubble-content">
                {renderBubbleContent(msg.content)}
              </span>
            )}
          </div>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
