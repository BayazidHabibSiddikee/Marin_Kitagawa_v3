import { useState } from 'react';

/* ── Timer Modal ─────────────────────────────────────────── */
interface TimerModalProps {
  open: boolean;
  onClose: () => void;
  onStart: (task: string) => void;
}

export function TimerModal({ open, onClose, onStart }: TimerModalProps) {
  const [task, setTask] = useState('');

  const handleStart = () => {
    onStart(task.trim() || 'Focus session');
    setTask('');
    onClose();
  };

  return (
    <div className={`marin-modal-overlay ${open ? 'open' : ''}`} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="marin-modal-box" style={{ maxWidth: 380 }}>
        <h3>Start focus session</h3>
        <input
          className="marin-modal-input"
          type="text"
          placeholder="What are you working on?"
          value={task}
          onChange={e => setTask(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleStart()}
          autoFocus
        />
        <div className="marin-modal-actions">
          <button className="mbtn-ghost" onClick={onClose}>cancel</button>
          <button className="mbtn-primary" onClick={handleStart}>start ▶</button>
        </div>
      </div>
    </div>
  );
}

/* ── Word Limit Modal ────────────────────────────────────── */
interface WordLimitModalProps {
  open: boolean;
  currentLimit: number;
  onClose: () => void;
  onApply: (limit: number) => void;
}

export function WordLimitModal({ open, currentLimit, onClose, onApply }: WordLimitModalProps) {
  const [val, setVal] = useState(String(currentLimit));

  const handleApply = () => {
    onApply(Math.max(0, parseInt(val) || 0));
    onClose();
  };

  return (
    <div className={`marin-modal-overlay ${open ? 'open' : ''}`} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="marin-modal-box" style={{ maxWidth: 320 }}>
        <h3>Word limit</h3>
        <p style={{ color: 'var(--text-dim)', fontSize: '.8rem', marginBottom: 12 }}>Set to 0 for no limit.</p>
        <input
          className="marin-modal-input"
          type="number"
          min={0}
          max={2000}
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleApply()}
          autoFocus
        />
        <div className="marin-modal-actions">
          <button className="mbtn-ghost" onClick={onClose}>cancel</button>
          <button className="mbtn-primary" onClick={handleApply}>apply</button>
        </div>
      </div>
    </div>
  );
}

/* ── Settings Modal ──────────────────────────────────────── */
type SettingsTab = 'general' | 'providers' | 'danger';

interface SettingsModalProps {
  open: boolean;
  onClose: () => void;
}

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const [tab, setTab] = useState<SettingsTab>('general');
  const [saved, setSaved] = useState(false);
  const [name, setName] = useState('');
  const [location, setLocation] = useState('');

  const handleSave = () => {
    setSaved(true);
    setTimeout(() => {
      setSaved(false);
      onClose();
    }, 800);
  };

  return (
    <div className={`marin-modal-overlay ${open ? 'open' : ''}`} onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="marin-modal-box" style={{ maxWidth: 540, maxHeight: '88vh', display: 'flex', flexDirection: 'column' }}>
        <h3 style={{ marginBottom: 0 }}>Settings</h3>

        {/* Tab bar */}
        <div style={{ display: 'flex', borderBottom: '1px solid var(--mborder)', marginBottom: 16, marginTop: 8 }}>
          {(['general', 'providers', 'danger'] as SettingsTab[]).map(t => (
            <button
              key={t}
              className={`mstab ${tab === t ? 'active' : ''}`}
              onClick={() => setTab(t)}
              style={t === 'danger' ? { marginLeft: 'auto', color: tab === 'danger' ? undefined : 'var(--mdanger)' } : undefined}
            >
              {t === 'danger' ? '⚠ Uninstall' : t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 12, paddingRight: 4 }}>
          {tab === 'general' && (
            <>
              <label className="mset-label">
                YOUR NAME
                <input
                  className="mset-input"
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Enter your name..."
                />
              </label>
              <label className="mset-label">
                LOCATION
                <input
                  className="mset-input"
                  type="text"
                  value={location}
                  onChange={e => setLocation(e.target.value)}
                  placeholder="City, Country"
                />
              </label>
              <label className="mset-label">
                VISION MODEL
                <input
                  className="mset-input"
                  type="text"
                  placeholder="meta-llama/llama-3.2-11b-vision-instruct:free"
                />
              </label>
              <label className="mset-label">
                IMAGE MODEL
                <input
                  className="mset-input"
                  type="text"
                  placeholder="black-forest-labs/flux-schnell"
                />
              </label>
              <label className="mset-label">
                HUGGINGFACE TOKEN
                <input
                  className="mset-input"
                  type="password"
                  placeholder="(optional, speeds up RAG)"
                />
              </label>
            </>
          )}

          {tab === 'providers' && (
            <>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {['OpenRouter', 'Google Gemini', 'OpenAI'].map((name, i) => (
                  <div key={name} className="mprovider-card enabled">
                    <div className="mprovider-header">
                      <div className="mprovider-dot on" />
                      <span className="mprovider-name">#{i + 1} {name}</span>
                      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '.6rem', color: 'var(--text-muted)' }}>
                        {i === 0 ? 'openrouter.ai' : i === 1 ? 'google.com' : 'openai.com'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              <button
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '.65rem',
                  padding: '6px 14px',
                  border: '1px dashed var(--mborder)',
                  background: 'transparent',
                  color: 'var(--text-dim)',
                  cursor: 'pointer',
                  letterSpacing: '.05em',
                  marginTop: 4,
                  borderRadius: 4,
                }}
              >
                + Add Provider
              </button>
            </>
          )}

          {tab === 'danger' && (
            <>
              <div style={{ fontSize: '.75rem', color: 'var(--mdanger)', fontFamily: "'JetBrains Mono', monospace", border: '1px solid var(--mdanger)', borderRadius: 6, padding: 10 }}>
                ⚠ These actions are irreversible.
              </div>
              {[
                { title: 'Clear FAISS Index', desc: 'Deletes all RAG vector index files from disk. Library will re-index on next document upload.' },
                { title: 'Clear HuggingFace Cache', desc: 'Deletes all downloaded model files from ~/.cache/huggingface.' },
                { title: 'Reset All Settings', desc: 'Wipes all API keys, providers, model selections, and state. Chat history is preserved.' },
              ].map(({ title, desc }) => (
                <div key={title} className="mdanger-card">
                  <div className="mdanger-card-title">{title}</div>
                  <div className="mdanger-card-desc">{desc}</div>
                  <button className="mbtn-danger">{title}</button>
                </div>
              ))}
            </>
          )}
        </div>

        {saved && (
          <p style={{ color: 'var(--teal)', fontSize: '.75rem', marginTop: 8 }}>Saved!</p>
        )}

        <div className="marin-modal-actions" style={{ marginTop: 16 }}>
          <button className="mbtn-ghost" onClick={onClose}>cancel</button>
          <button className="mbtn-primary" onClick={handleSave}>save</button>
        </div>
      </div>
    </div>
  );
}

/* ── Terminal Panel ──────────────────────────────────────── */
export interface TermEntry {
  id: string;
  timestamp: string;
  text: string;
  type: 'cmd' | 'info' | 'warn' | 'ok';
}

interface TerminalPanelProps {
  visible: boolean;
  entries: TermEntry[];
  onClose: () => void;
}

export function TerminalPanel({ visible, entries, onClose }: TerminalPanelProps) {
  if (!visible) return null;

  const typeColor = (t: TermEntry['type']) => {
    if (t === 'cmd') return 'var(--teal)';
    if (t === 'warn') return 'var(--gold)';
    if (t === 'ok') return 'var(--msuccess)';
    return 'var(--text-dim)';
  };

  return (
    <div className="marin-term-panel">
      <div className="mterm-header">
        <span>command log</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ color: 'var(--text-muted)' }}>{entries.length} entries</span>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: '1px solid var(--mborder)',
              color: 'var(--text-dim)',
              padding: '2px 8px',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: '.6rem',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            ✕
          </button>
        </div>
      </div>
      <div className="mterm-entries">
        {entries.length === 0 ? (
          <span style={{ color: 'var(--text-muted)' }}>No entries yet...</span>
        ) : (
          entries.map(e => (
            <div key={e.id} className="mterm-entry">
              <span className="ts">[{e.timestamp}]</span>{' '}
              <span style={{ color: typeColor(e.type) }}>{e.text}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
