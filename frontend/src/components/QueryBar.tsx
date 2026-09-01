import React, { useState } from "react";

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
}

export function QueryBar({ onSubmit, disabled }: Props) {
  const [query, setQuery] = useState("");

  const submit = () => {
    const q = query.trim();
    if (q) onSubmit(q);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !disabled && submit()}
          placeholder="Ask a question about your satellite image(s)…"
          disabled={disabled}
          style={{
            flex: 1,
            padding: "10px 14px",
            fontSize: 14,
            border: "1px solid #d1d5db",
            borderRadius: 8,
            outline: "none",
            background: disabled ? "#f9fafb" : "#fff",
          }}
        />
        <button
          onClick={submit}
          disabled={disabled || !query.trim()}
          style={{
            padding: "10px 20px",
            background: disabled || !query.trim() ? "#9ca3af" : "#0284c7",
            color: "#fff",
            border: "none",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            cursor: disabled || !query.trim() ? "not-allowed" : "pointer",
            whiteSpace: "nowrap",
          }}
        >
          Analyse
        </button>
      </div>

      {/* Example queries */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => setQuery(q)}
            disabled={disabled}
            style={{
              fontSize: 11,
              padding: "3px 8px",
              background: "#f0f9ff",
              border: "1px solid #bae6fd",
              borderRadius: 20,
              color: "#0369a1",
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}
