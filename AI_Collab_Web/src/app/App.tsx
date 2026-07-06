import { useState, useEffect, useRef, useCallback } from 'react';
import '../styles/marin.css';
import { TopBar } from './components/TopBar';
import { IntelTicker } from './components/IntelTicker';
import { TimerStrip } from './components/TimerStrip';
import { Sidebar } from './components/Sidebar';
import { ChatMessages, type Message } from './components/ChatMessages';
import { InputArea } from './components/InputArea';
import { TimerModal, WordLimitModal, SettingsModal, TerminalPanel, type TermEntry } from './components/Modals';

const DEPTHS = ['standard', 'detailed', 'cascade'] as const;
type Depth = typeof DEPTHS[number];

let msgCounter = 0;
const uid = () => `m${++msgCounter}_${Date.now()}`;

const now = () => new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

const MOCK_RESPONSES: Record<string, string> = {
  greet: "Hello! I'm Marin, your intelligence assistant. I'm fully operational and ready to help with analysis, research, creative tasks, or just a good conversation. What can I do for you today?",
  time: `The current time is ${new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })} on ${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' })}.`,
  help: `Here's what I can help you with:\n\n**Core capabilities:**\n- Deep research and analysis\n- Code review and generation\n- Creative writing and ideation\n- Data interpretation\n- Strategic planning\n\n**Commands:**\n- /timer start [task] — begin a focus session\n- /timer stop — end current session\n- /timer status — view session stats\n- /habits status — check your habits\n\nJust type naturally or use any of the commands above.`,
  model: "Model switching is available in the sidebar. Select from Marin, Aera, Dahlia, Lyra, and many others — each with distinct personality profiles and capability sets.",
  action: "Animation control is active. The VRM avatar system supports full BVH motion capture animations. Toggle the avatar panel to see it live.",
  dance: "Dancing! The motion system is queued. Gangnam Style and Rumba are perennial favorites.",
  emotion: "Emotional expression registered. The affect system maps to facial blend shapes and body language in the VRM model.",
  timer_resume: "Checking your last session... No active session found. Use the **▶ start** button in the timer strip to begin a new focus block.",
  timer_status: "**Session status:** Idle\n\n*Today's tracked time:* 0m\n*Sessions completed:* 0\n\nStart a focus session to begin tracking your work time.",
  habits: "**Habit tracker summary:**\n\n*Morning routine:* ○ Not logged today\n*Deep work block:* ○ Not started\n*Reading:* ○ Pending\n\nNo habits configured yet. You can set up your routine in the settings panel.",
  brief: `**Daily Intelligence Brief — ${new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}**\n\n*Weather:* Data unavailable (location not set)\n*Tasks today:* 0 active\n*Sessions logged:* 0\n\nConfigure your location in settings to unlock weather and personalized briefings.`,
};

const GENERIC_RESPONSES = [
  "That's a thoughtful prompt. Let me reason through this systematically.\n\nThe core of what you're asking touches on several interconnected ideas. The most direct path forward involves understanding the underlying structure first — then we can work outward toward the specific application you have in mind.\n\nWhat aspect would you like me to expand on first?",
  "I've processed that. Here's my analysis:\n\nThere are a few different angles worth considering here. The conventional approach has merit, but there are some non-obvious optimizations that could make a significant difference depending on your constraints.\n\nWant me to walk through them in detail, or would a high-level summary serve better?",
  "Interesting. This connects to a pattern I've seen before in related domains.\n\nThe key insight is that the surface-level framing can be misleading — the *actual* leverage point is usually one level deeper. Once you identify that, the solution space becomes much cleaner.\n\nLet me map out the landscape for you.",
  "Good question. The short answer is: it depends on context. The longer answer is more useful.\n\nA few dimensions matter here: **scope**, **constraints**, and **time horizon**. These interact in non-obvious ways. Getting clarity on all three usually resolves what initially looks like a hard problem.\n\nWhich of these is the binding constraint in your situation?",
  "I can help with that. Let me think out loud for a moment.\n\nAt first glance this seems like a [type A] problem, but the deeper structure is more like a [type B] problem in disguise. The distinction matters because the failure modes are different and the solutions don't overlap much.\n\nThe path I'd recommend: start with the simplest viable version, validate the core assumption, then layer in complexity only where the data demands it.",
  "Noted. Processing.\n\nThere's a rich body of work on exactly this kind of problem. The consensus has shifted in the last few years — the old orthodoxy was [approach X], but more recent evidence points strongly toward [approach Y].\n\nThe practical upshot: you're probably closer to the right answer than you think. The main adjustments I'd suggest are refinements, not overhauls.",
  "That's within my wheelhouse. Here's a structured breakdown:\n\n1. **First principle** — The foundational constraint you need to respect\n2. **Key tradeoff** — What you gain and lose with different approaches  \n3. **Recommended path** — The highest-expected-value option given typical constraints\n4. **Watch-outs** — The failure modes that aren't obvious until it's too late\n\nWant me to elaborate on any of these?",
];

function getMockResponse(input: string): string {
  const lower = input.toLowerCase().trim();

  if (/^(hi|hello|hey|greetings|sup|yo)\b/.test(lower)) return MOCK_RESPONSES.greet;
  if (/time|date|day|today/.test(lower)) return MOCK_RESPONSES.time;
  if (/help|what can you|capabilities|commands/.test(lower)) return MOCK_RESPONSES.help;
  if (/^\/model/.test(lower)) return MOCK_RESPONSES.model;
  if (/^\/action/.test(lower)) return MOCK_RESPONSES.action;
  if (/^\/dance/.test(lower)) return MOCK_RESPONSES.dance;
  if (/^\/emotion/.test(lower)) return MOCK_RESPONSES.emotion;
  if (/^\/timer resume/.test(lower)) return MOCK_RESPONSES.timer_resume;
  if (/^\/timer status/.test(lower)) return MOCK_RESPONSES.timer_status;
  if (/^\/habits status/.test(lower)) return MOCK_RESPONSES.habits;
  if (/^\/habits stats/.test(lower)) return MOCK_RESPONSES.brief;

  return GENERIC_RESPONSES[Math.floor(Math.random() * GENERIC_RESPONSES.length)];
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

const INITIAL_MESSAGES: Message[] = [
  {
    id: uid(),
    role: 'ai',
    content: '**Marin is online.**\nReady when you are. Switch modes from the sidebar, or just start typing.\n\n*Commands: /timer start [task] · /timer stop · /timer stats*',
  },
];

export default function App() {
  const [nightMode, setNightMode] = useState(() => localStorage.getItem('marinNightMode') === 'true');
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [isStreaming, setIsStreaming] = useState(false);
  const [depth, setDepth] = useState<Depth>('standard');
  const [wordLimit, setWordLimit] = useState(0);
  const [voiceOn, setVoiceOn] = useState(false);
  const [ragEnabled, setRagEnabled] = useState(false);
  const [termVisible, setTermVisible] = useState(false);
  const [termEntries, setTermEntries] = useState<TermEntry[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [showTimer, setShowTimer] = useState(false);
  const [showWordLimit, setShowWordLimit] = useState(false);
  const [timerRunning, setTimerRunning] = useState(false);
  const [sessionSeconds, setSessionSeconds] = useState(0);
  const [sessionTask, setSessionTask] = useState('idle');
  const [todaySeconds, setTodaySeconds] = useState(0);

  const streamRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    localStorage.setItem('marinNightMode', String(nightMode));
  }, [nightMode]);

  useEffect(() => {
    return () => {
      if (streamRef.current) clearInterval(streamRef.current);
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const addTermEntry = useCallback((text: string, type: TermEntry['type'] = 'info') => {
    setTermEntries(prev => [...prev, { id: uid(), timestamp: now(), text, type }]);
  }, []);

  const handleSend = useCallback((text: string) => {
    if (isStreaming) return;

    const userMsg: Message = { id: uid(), role: 'user', content: text };
    const typingId = uid();
    const typingMsg: Message = { id: typingId, role: 'ai', content: '', isTyping: true };

    setMessages(prev => [...prev, userMsg, typingMsg]);
    setIsStreaming(true);
    addTermEntry(`user: ${text.slice(0, 60)}${text.length > 60 ? '...' : ''}`, 'cmd');

    const delay = 700 + Math.random() * 800;

    setTimeout(() => {
      let response = getMockResponse(text);
      if (wordLimit > 0) {
        const words = response.split(/\s+/);
        if (words.length > wordLimit) {
          response = words.slice(0, wordLimit).join(' ') + '…';
        }
      }

      const streamMsgId = uid();
      setMessages(prev =>
        prev.map(m => m.id === typingId ? { ...m, id: streamMsgId, isTyping: false, content: '' } : m)
      );

      let i = 0;
      streamRef.current = setInterval(() => {
        i++;
        setMessages(prev =>
          prev.map(m => m.id === streamMsgId ? { ...m, content: response.slice(0, i) } : m)
        );
        if (i >= response.length) {
          clearInterval(streamRef.current!);
          setIsStreaming(false);
          addTermEntry('ai: response complete', 'ok');
        }
      }, 12);
    }, delay);
  }, [isStreaming, wordLimit, addTermEntry]);

  const handleSidebarAction = useCallback((action: string) => {
    handleSend(action);
  }, [handleSend]);

  const handleStartTimer = (task: string) => {
    setSessionTask(task);
    setSessionSeconds(0);
    setTimerRunning(true);
    addTermEntry(`/timer start "${task}"`, 'cmd');

    timerRef.current = setInterval(() => {
      setSessionSeconds(s => s + 1);
      setTodaySeconds(t => t + 1);
    }, 1000);
  };

  const handleStopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setTimerRunning(false);
    addTermEntry(`/timer stop — session: ${formatDuration(sessionSeconds)}`, 'ok');
    setSessionTask('idle');
  };

  const cycleDepth = () => {
    setDepth(prev => {
      const idx = DEPTHS.indexOf(prev);
      const next = DEPTHS[(idx + 1) % DEPTHS.length];
      addTermEntry(`depth set to ${next}`, 'info');
      return next;
    });
  };

  const formatTodayTotal = () => {
    const m = Math.floor(todaySeconds / 60);
    if (m < 60) return `${m}m`;
    return `${Math.floor(m / 60)}h ${m % 60}m`;
  };

  return (
    <div className={`marin-app ${nightMode ? 'night' : ''}`}>
      <div className="marin-grain" />

      <TopBar
        agentName="Marin"
        agentBadge="HS-02 · ONLINE"
        voiceOn={voiceOn}
        ragEnabled={ragEnabled}
        termVisible={termVisible}
        nightMode={nightMode}
        isStreaming={isStreaming}
        onToggleVoice={() => {
          setVoiceOn(v => !v);
          addTermEntry(`voice ${!voiceOn ? 'enabled' : 'disabled'}`, 'info');
        }}
        onToggleRag={() => {
          setRagEnabled(r => !r);
          addTermEntry(`rag ${!ragEnabled ? 'enabled' : 'disabled'}`, 'info');
        }}
        onToggleTerm={() => setTermVisible(v => !v)}
        onToggleNight={() => setNightMode(n => !n)}
        onOpenSettings={() => setShowSettings(true)}
      />

      <IntelTicker />

      <TimerStrip
        sessionTime={timerRunning ? formatDuration(sessionSeconds) : '--:--'}
        sessionTask={sessionTask}
        todayTotal={formatTodayTotal()}
        timerRunning={timerRunning}
        onOpenTimer={() => setShowTimer(true)}
        onStopTimer={handleStopTimer}
      />

      <div className="marin-main">
        <Sidebar onSendAction={handleSidebarAction} />

        <div className="marin-chat-wrapper">
          <ChatMessages messages={messages} />

          <div className="marin-mode-bar">
            <button className="marin-mode-tab active">chat</button>
          </div>

          <InputArea
            onSend={handleSend}
            disabled={isStreaming}
            depth={depth}
            onCycleDepth={cycleDepth}
            wordLimit={wordLimit}
            onOpenWordLimit={() => setShowWordLimit(true)}
          />
        </div>
      </div>

      <TimerModal
        open={showTimer}
        onClose={() => setShowTimer(false)}
        onStart={handleStartTimer}
      />

      <WordLimitModal
        open={showWordLimit}
        currentLimit={wordLimit}
        onClose={() => setShowWordLimit(false)}
        onApply={setWordLimit}
      />

      <SettingsModal
        open={showSettings}
        onClose={() => setShowSettings(false)}
      />

      <TerminalPanel
        visible={termVisible}
        entries={termEntries}
        onClose={() => setTermVisible(false)}
      />
    </div>
  );
}
