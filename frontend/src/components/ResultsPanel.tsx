import { useState } from "react";
import type { JobResultResponse } from "../types";

interface Props {
  result: JobResultResponse | null;
  status: string;
  progressMessage: string;
}

export function ResultsPanel({ result, status, progressMessage }: Props) {
  const [showTrace, setShowTrace] = useState(false);

  if (!result && status === "PENDING") return null;

  if (["PENDING", "VALIDATING", "PLANNING", "RUNNING", "FUSING"].includes(status)) {
    return (
      <div className="result-card loading-card">
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="loading-orb">◌</span>
          <div>
            <p className="result-title">{statusLabel(status)}</p>
            <p className="result-muted">{progressMessage}</p>
          </div>
        </div>
      </div>
    );
  }

  if (status === "FAILED") {
    return (
      <div className="result-card failed-card">
      <p className="result-title">Analysis failed</p>
      <p className="result-muted">
          {result?.error ?? "Unknown error"}
        </p>
      </div>
    );
  }

  if (!result?.evidence) return null;
  const ev = result.evidence;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Answer card */}
      <div className="result-card answer-card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
          <span className="eyebrow">
            {taskLabel(ev.task)}
          </span>
          <ConfidenceBadge confidence={ev.confidence} />
        </div>
        <p className="answer-text">{ev.answer}</p>
        {ev.confidence_rationale && (
          <p className="result-muted rationale">{ev.confidence_rationale}</p>
        )}
      </div>

      {/* Detected regions */}
      {ev.detected_regions.length > 0 && (
        <div className="result-card">
          <p style={sectionTitle}>Detected Regions</p>
          <div className="region-list">
            {ev.detected_regions.map((r, i) => (
              <div key={i} className="region-row">
                <span className="region-label">{r.label}</span>
                <span className="result-muted">
                  {r.area_km2 != null ? `${r.area_km2.toFixed(2)} km²` : ""}
                  {r.score > 0 ? ` · ${(r.score * 100).toFixed(0)}%` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Overlay paths */}
      {(ev.change_map_path || ev.overlay_path) && (
        <div className="result-card">
          <p style={sectionTitle}>Spatial Outputs</p>
          {ev.change_map_path && (
            <p className="output-line">
              📍 Change map available — visible on map viewer
            </p>
          )}
          {ev.overlay_path && (
            <p className="output-line">
              🗺 Segmentation overlay available — visible on map viewer
            </p>
          )}
        </div>
      )}

      {/* Models used */}
      <div className="result-card">
        <p style={sectionTitle}>Models Used</p>
        <div className="model-tags">
          {ev.models_used.map((m) => (
            <span key={m} className="model-tag">{m.split(":")[0]}</span>
          ))}
        </div>
      </div>

      {/* Execution trace toggle */}
      <button
        onClick={() => setShowTrace((v) => !v)}
        className="trace-button"
      >
        {showTrace ? "▲ Hide" : "▼ Show"} execution trace
      </button>

      {showTrace && ev.execution_plan && (
        <div className="result-card trace-card">
          <pre className="trace-output">
            {JSON.stringify(ev.execution_plan, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color = pct >= 70 ? "#16a34a" : pct >= 40 ? "#d97706" : "#dc2626";
  return (
    <span style={{ fontSize: 12, fontWeight: 700, color, background: color + "18", padding: "2px 8px", borderRadius: 20 }}>
      {pct}% confidence
    </span>
  );
}

function statusLabel(s: string): string {
  const map: Record<string, string> = {
    PENDING: "Queued",
    VALIDATING: "Validating inputs…",
    PLANNING: "Planning analysis…",
    RUNNING: "Running models…",
    FUSING: "Fusing evidence…",
  };
  return map[s] ?? s;
}

function taskLabel(t: string): string {
  const map: Record<string, string> = {
    SINGLE_VQA: "Visual Q&A",
    SINGLE_CAPTION: "Scene Caption",
    SINGLE_GROUNDING: "Region Grounding",
    BITEMPORAL_CHANGE_DETECT: "Change Detection",
    BITEMPORAL_CHANGE_VQA: "Change Q&A",
    CROSS_MODAL_ANALYSIS: "Optical + SAR Analysis",
  };
  return map[t] ?? t;
}

const sectionTitle: React.CSSProperties = {
  margin: "0 0 10px",
};
