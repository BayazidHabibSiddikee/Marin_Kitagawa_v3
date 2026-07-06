import { useRef, useState, KeyboardEvent } from 'react';

const DEPTHS = ['standard', 'detailed', 'cascade'] as const;
type Depth = typeof DEPTHS[number];

interface InputAreaProps {
  onSend: (text: string) => void;
  disabled: boolean;
  depth: Depth;
  onCycleDepth: () => void;
  wordLimit: number;
  onOpenWordLimit: () => void;
}

export function InputArea({
  onSend,
  disabled,
  depth,
  onCycleDepth,
  wordLimit,
  onOpenWordLimit,
}: InputAreaProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 130) + 'px';
  };

  return (
    <div className="marin-input-area">
      <div className="marin-input-row">
        <textarea
          ref={textareaRef}
          className="marin-textarea"
          rows={1}
          placeholder="Ask anything..."
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={disabled}
        />
        <button
          className="marin-send-btn"
          onClick={handleSend}
          disabled={disabled || !value.trim()}
        >
          send
        </button>
      </div>
      <div className="marin-tools-row">
        <button className="mtool-btn" onClick={onCycleDepth}>
          depth: {depth}
        </button>
        <button className="mtool-btn" onClick={onOpenWordLimit}>
          {wordLimit > 0 ? `limit: ${wordLimit}w` : 'limit: free'}
        </button>
        <span className="mhint-text">enter · shift+enter for newline</span>
      </div>
    </div>
  );
}
