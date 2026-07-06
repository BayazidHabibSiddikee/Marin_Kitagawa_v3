interface TimerStripProps {
  sessionTime: string;
  sessionTask: string;
  todayTotal: string;
  timerRunning: boolean;
  onOpenTimer: () => void;
  onStopTimer: () => void;
}

export function TimerStrip({
  sessionTime,
  sessionTask,
  todayTotal,
  timerRunning,
  onOpenTimer,
  onStopTimer,
}: TimerStripProps) {
  return (
    <div className="marin-timer-strip">
      <span className="mts-lbl">SESSION</span>
      <span className="mts-val">{sessionTime}</span>
      <span className="mts-sep">·</span>
      <span className="mts-lbl">TASK</span>
      <span className="mts-task">{sessionTask}</span>
      <span className="mts-sep">·</span>
      <span className="mts-lbl">TODAY</span>
      <span className="mts-val">{todayTotal}</span>
      {timerRunning ? (
        <button className="mts-btn stop" onClick={onStopTimer}>
          ■ stop
        </button>
      ) : (
        <button className="mts-btn start" onClick={onOpenTimer}>
          ▶ start
        </button>
      )}
    </div>
  );
}
