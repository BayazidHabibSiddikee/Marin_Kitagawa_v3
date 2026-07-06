import { useState } from 'react';

interface SidebarProps {
  onSendAction: (action: string) => void;
}

type DropdownKey = 'models' | 'actions' | 'dances' | 'emotions' | 'idles';

const MODELS = [
  'Marin (Default)', 'Aera', 'Dahlia', 'Epithet', 'Lara', 'Onyx', 'Velara',
  'Seraph', 'Nova', 'Lyra ★', 'Zara',
];

const ACTIONS = [
  'Attention Seeking', 'Crawling', 'Crouch', 'Gaming', 'Greeting',
  'Jog', 'Jump', 'Laydown', 'Pat', 'Run', 'Standup', 'Walk',
];

const DANCES = [
  'Dance 1', 'Dance 2', 'Backup', 'Dab', 'Gangnam Style',
  'Headdrop', 'Marachinostep', 'Northern Soul Spin', 'Rumba',
];

const EMOTIONS = [
  'Admiration', 'Anger', 'Caring', 'Confusion', 'Curiosity', 'Desire',
  'Disappointment', 'Disgust', 'Embarrassment', 'Excitement', 'Fear',
  'Gratitude', 'Grief', 'Joy', 'Love', 'Nervousness', 'Optimism',
  'Pride', 'Realization', 'Relief', 'Remorse', 'Sadness', 'Surprise',
];

const IDLES = ['Kneel Idle', 'Laying Idle', 'Neutral Idle', 'Sit Idle'];

export function Sidebar({ onSendAction }: SidebarProps) {
  const [openDropdown, setOpenDropdown] = useState<DropdownKey | null>(null);

  const toggleDropdown = (key: DropdownKey) => {
    setOpenDropdown(prev => (prev === key ? null : key));
  };

  return (
    <aside className="marin-sidebar">
      <div className="msb-section">Navigate</div>
      <button className="msb-btn active">
        <span className="msb-icon">◈</span> Chat
      </button>
      <button className="msb-btn" onClick={() => onSendAction('/habits status')}>
        <span className="msb-icon">◉</span> Profile
      </button>

      <div className="msb-section">Proactive</div>
      <button className="msb-btn" onClick={() => onSendAction('/habits status')}>
        <span className="msb-icon">📋</span> Check Todos
      </button>
      <button className="msb-btn" onClick={() => onSendAction('/timer resume')}>
        <span className="msb-icon">🔄</span> Resume Session
      </button>
      <button className="msb-btn" onClick={() => onSendAction('/habits stats')}>
        <span className="msb-icon">📊</span> Daily Brief
      </button>
      <button className="msb-btn" onClick={() => onSendAction('/timer status')}>
        <span className="msb-icon">⏱️</span> Timer Status
      </button>

      {/* Models Dropdown */}
      <button className="msb-btn" onClick={() => toggleDropdown('models')}>
        <span className="msb-icon">👤</span> Models
        <span className="msb-arrow" style={{ transform: openDropdown === 'models' ? 'rotate(180deg)' : undefined }}>▼</span>
      </button>
      <div className={`msb-dropdown ${openDropdown === 'models' ? 'open' : ''}`}>
        {MODELS.map(m => (
          <button
            key={m}
            className="msb-btn"
            style={m === 'Lyra ★' ? { color: 'var(--teal)' } : undefined}
            onClick={() => onSendAction(`/model ${m.replace(' ★', '')}`)}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Actions Dropdown */}
      <button className="msb-btn" onClick={() => toggleDropdown('actions')}>
        <span className="msb-icon">🏃</span> Actions
        <span className="msb-arrow" style={{ transform: openDropdown === 'actions' ? 'rotate(180deg)' : undefined }}>▼</span>
      </button>
      <div className={`msb-dropdown ${openDropdown === 'actions' ? 'open' : ''}`}>
        {ACTIONS.map(a => (
          <button key={a} className="msb-btn" onClick={() => onSendAction(`/action ${a.toLowerCase()}`)}>
            {a}
          </button>
        ))}
      </div>

      {/* Dances Dropdown */}
      <button className="msb-btn" onClick={() => toggleDropdown('dances')}>
        <span className="msb-icon">💃</span> Dances
        <span className="msb-arrow" style={{ transform: openDropdown === 'dances' ? 'rotate(180deg)' : undefined }}>▼</span>
      </button>
      <div className={`msb-dropdown ${openDropdown === 'dances' ? 'open' : ''}`}>
        {DANCES.map(d => (
          <button key={d} className="msb-btn" onClick={() => onSendAction(`/dance ${d.toLowerCase()}`)}>
            {d}
          </button>
        ))}
      </div>

      {/* Emotions Dropdown */}
      <button className="msb-btn" onClick={() => toggleDropdown('emotions')}>
        <span className="msb-icon">😊</span> Emotions
        <span className="msb-arrow" style={{ transform: openDropdown === 'emotions' ? 'rotate(180deg)' : undefined }}>▼</span>
      </button>
      <div className={`msb-dropdown ${openDropdown === 'emotions' ? 'open' : ''}`}>
        {EMOTIONS.map(e => (
          <button key={e} className="msb-btn" onClick={() => onSendAction(`/emotion ${e.toLowerCase()}`)}>
            {e}
          </button>
        ))}
      </div>

      {/* Idles Dropdown */}
      <button className="msb-btn" onClick={() => toggleDropdown('idles')}>
        <span className="msb-icon">🧍</span> Idles
        <span className="msb-arrow" style={{ transform: openDropdown === 'idles' ? 'rotate(180deg)' : undefined }}>▼</span>
      </button>
      <div className={`msb-dropdown ${openDropdown === 'idles' ? 'open' : ''}`}>
        {IDLES.map(i => (
          <button key={i} className="msb-btn" onClick={() => onSendAction(`/idle ${i.toLowerCase()}`)}>
            {i}
          </button>
        ))}
      </div>

      <div className="msb-section">Status</div>
      <div style={{
        padding: '10px 16px',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: '0.65rem',
        color: 'var(--text-dim)',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--msuccess)', boxShadow: '0 0 6px var(--msuccess)', display: 'inline-block', animation: 'mpip 2.5s infinite' }} />
          <span>Synthesizing intelligence...</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--gold)', boxShadow: '0 0 6px var(--gold)', display: 'inline-block' }} />
          <span>Awaiting user directive...</span>
        </div>
      </div>
    </aside>
  );
}
