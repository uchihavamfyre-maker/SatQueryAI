const EXAMPLE_QUERIES = [
  "What land cover type dominates this image?",
  "Describe the scene in this satellite image.",
  "Locate all water bodies in this image.",
  "What changed between these two images?",
  "Did urban area expand between T1 and T2?",
  "Identify built-up areas and water regions using both optical and SAR images.",
];

interface Props {
  onSubmit: (query: string) => void;
  disabled: boolean;
  value: string;
  onChange: (query: string) => void;
}

export function QueryBar({ onSubmit, disabled, value, onChange }: Props) {

  const submit = () => {
    const q = value.trim();
    if (q) onSubmit(q);
  };

  return (
    <div className="query-bar">
      <div className="query-row">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !disabled && submit()}
          placeholder="Ask a question about your satellite image(s)…"
          disabled={disabled}
          className="query-input"
        />
        <button
          onClick={submit}
          disabled={disabled || !value.trim()}
          className="primary-button"
        >
          Analyse
        </button>
      </div>

      {/* Example queries */}
      <div className="suggestions">
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => onChange(q)}
            disabled={disabled}
            className="suggestion-chip"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
