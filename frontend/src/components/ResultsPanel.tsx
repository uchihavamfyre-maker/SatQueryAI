import React, { useState } from "react";
import type { EvidenceObject, JobResultResponse } from "../types";

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
      <div style={cardStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 20 }}>⏳</span>
          <div>
            <p style={{ margin: 0, fontWeight: 600, fontSize: 14 }}>{statusLabel(status)}</p>
            <p style={{ margin: 0, fontSize: 12, color: "#6b7280" }}>{progressMessage}</p>
          </div>
        </div>
      </div>
    );
  }

  if (status === "FAILED") {
    return (
      <div style={{ ...cardStyle, borderColor: "#fca5a5", background: "#fff1f2" }}>
        <p style={{ margin: 0, fontWeight: 600, color: "#dc2626" }}>Analysis failed</p>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "#6b7280" }}>
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
      <div style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: "#0369a1", textTransform: "uppercase", letterSpacing: 1 }}>
            {taskLabel(ev.task)}
          </span>
          <ConfidenceBadge confidence={ev.confidence} />
        </div>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "#111827" }}>{ev.answer}</p>
        {ev.confidence_rationale && (
          <p style={{ margin: "8px 0 0", fontSize: 11, color: "#9ca3af" }}>{ev.confidence_rationale}</p>
        )}
      </div>

      {/* Detected regions */}
      {ev.detected_regions.length > 0 && (
        <div style={cardStyle}>
          <p style={sectionTitle}>Detected Regions</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {ev.detected_regions.map((r, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 13 }}>
                <span style={{ fontWeight: 500, textTransform: "capitalize" }}>{r.label}</span>
                <span style={{ color: "#6b7280" }}>
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
        <div style={cardStyle}>
          <p style={sectionTitle}>Spatial Outputs</p>
          {ev.change_map_path && (
            <p style={{ margin: 0, fontSize: 12, color: "#0284c7" }}>
              📍 Change map available — visible on map viewer
            </p>
          )}
          {ev.overlay_path && (
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "#0284c7" }}>
              🗺 Segmentation overlay available — visible on map viewer
            </p>
          )}
        </div>
      )}

      {/* Models used */}
      <div style={cardStyle}>
        <p style={sectionTitle}>Models Used</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {ev.models_used.map((m) => (
            <span key={m} style={tagStyle}>{m.split(":")[0]}</span>
          ))}
        </div>
      </div>

      {/* Execution trace toggle */}
      <button
        onClick={() => setShowTrace((v) => !v)}
        style={{
          background: "none",
          border: "1px solid #e5e7eb",
          borderRadius: 8,
          padding: "8px 12px",
          fontSize: 12,
          color: "#6b7280",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        {showTrace ? "▲ Hide" : "▼ Show"} execution trace
      </button>

      {showTrace && ev.execution_plan && (
        <div style={{ ...cardStyle, background: "#0f172a" }}>
          <pre style={{ margin: 0, fontSize: 11, color: "#94a3b8", overflowX: "auto", whiteSpace: "pre-wrap" }}>
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

const cardStyle: React.CSSProperties = {
  background: "#fff",
  border: "1px solid #e5e7eb",
  borderRadius: 10,
  padding: "14px 16px",
};

const sectionTitle: React.CSSProperties = {
  margin: "0 0 8px",
  fontSize: 11,
  fontWeight: 700,
  color: "#6b7280",
  textTransform: "uppercase",
  letterSpacing: 1,
};

const tagStyle: React.CSSProperties = {
  fontSize: 11,
  padding: "2px 8px",
  background: "#f0f9ff",
  border: "1px solid #bae6fd",
  borderRadius: 20,
  color: "#0369a1",
};
