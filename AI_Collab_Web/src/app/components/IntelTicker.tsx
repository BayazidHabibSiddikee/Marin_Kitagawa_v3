const TICKER_ITEMS = [
  'Gemini 2.5 Pro achieves new MMLU benchmarks',
  'Claude 4.0 context window expanded to 2M tokens',
  "LeCun's World Model paper cited 1,400 times in 72h",
  'DeepSeek R3 training run detected on distributed infrastructure',
  'Sora video generation API opens to enterprise partners',
  'Llama 4 shows emergent reasoning on novel mathematical tasks',
  'EU AI Act enforcement deadline passes without major incidents',
  'NVIDIA H200 allocation queue at 18 months for tier-1 customers',
  'Anthropic Constitutional AI v3 white paper published',
  'Mixtral 8x22b quantized version breaks mobile inference records',
  'GPT-5 Turbo demonstrates 10x token throughput improvement',
  'Open-source Phi-4 outperforms closed models on coding benchmarks',
  'Qwen3 480B MoE achieves near-human performance on ARC-AGI',
  'Meta releases Segment Anything Model 3 with video support',
  'HuggingFace downloads surpass 5 billion model pull requests',
];

export function IntelTicker() {
  const text = TICKER_ITEMS.join('  ·  ');

  return (
    <div className="marin-intel-bar">
      <span className="marin-intel-label">FEED</span>
      <div className="marin-news-ticker">
        <span className="marin-news-scroll">{text}</span>
      </div>
    </div>
  );
}
