interface TopBarProps {
  agentName: string;
  agentBadge: string;
  voiceOn: boolean;
  ragEnabled: boolean;
  termVisible: boolean;
  nightMode: boolean;
  isStreaming: boolean;
  onToggleVoice: () => void;
  onToggleRag: () => void;
  onToggleTerm: () => void;
  onToggleNight: () => void;
  onOpenSettings: () => void;
}

export function TopBar({
  agentName,
  agentBadge,
  voiceOn,
  ragEnabled,
  termVisible,
  nightMode,
  isStreaming,
  onToggleVoice,
  onToggleRag,
  onToggleTerm,
  onToggleNight,
  onOpenSettings,
}: TopBarProps) {
  return (
    <header className={`marin-topbar ${isStreaming ? 'marin-thinking' : ''}`}>
      <div className="marin-logo">
        <div className="marin-logo-avatar">
          <span style={{ fontFamily: "'DM Serif Display', serif", fontSize: '1.1rem', color: 'white' }}>
            M
          </span>
        </div>
        <div className="marin-logo-text">
          <span className="marin-logo-name">{agentName}</span>
          <span className="marin-logo-sub">{agentBadge}</span>
        </div>
      </div>

      <div className="marin-topbar-right">
        <button className="mtb-btn" onClick={onOpenSettings}>settings</button>
        <button className="mtb-btn" onClick={onToggleNight}>
          {nightMode ? 'day mode' : 'night mode'}
        </button>
        <button
          className={`mtb-btn ${voiceOn ? 'active-voice' : ''}`}
          onClick={onToggleVoice}
        >
          {voiceOn ? '◉ voice on' : 'voice'}
        </button>
        <button
          className={`mtb-btn ${ragEnabled ? 'active-rag' : ''}`}
          onClick={onToggleRag}
        >
          {ragEnabled ? '◉ rag on' : 'rag'}
        </button>
        <button
          className={`mtb-btn ${termVisible ? 'active' : ''}`}
          onClick={onToggleTerm}
        >
          log
        </button>
        <div className="marin-pip" title="Operational" />
      </div>
    </header>
  );
}
