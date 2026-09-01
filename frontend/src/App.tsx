import React, { useState } from "react";
import { ImageUploadPanel } from "./components/ImageUploadPanel";
import { QueryBar } from "./components/QueryBar";
import { ResultsPanel } from "./components/ResultsPanel";
import { MapViewer } from "./components/MapViewer";
import { pollUntilDone, submitQuery } from "./api/client";
import type { JobResultResponse, JobStatusResponse, UploadedImage } from "./types";
import { v4 as uuidv4 } from "./utils/uuid";

export default function App() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [result, setResult] = useState<JobResultResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const handleQuery = async (query: string) => {
    if (images.length === 0) {
      setGlobalError("Upload at least one image before querying.");
      return;
    }
    setGlobalError(null);
    setResult(null);
    setRunning(true);

    const jobId = uuidv4();
    const imageRoles: Record<string, string> = {};
    images.forEach((img) => {
      imageRoles[img.uploadId] = img.role;
    });

    try {
      await submitQuery({ job_id: jobId, query, image_roles: imageRoles });

      const finalResult = await pollUntilDone(
        jobId,
        (status) => setJobStatus(status),
      );
      setResult(finalResult);
      setJobStatus((prev) =>
        prev ? { ...prev, status: finalResult.status } : null,
      );
    } catch (e: unknown) {
      setGlobalError((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#f8fafc", fontFamily: "system-ui, sans-serif" }}>
      {/* Header */}
      <header
        style={{
          background: "#0c4a6e",
          color: "#fff",
          padding: "14px 24px",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <span style={{ fontSize: 24 }}>🛰️</span>
        <div>
          <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, letterSpacing: 0.5 }}>
            SatQuery AI
          </h1>
          <p style={{ margin: 0, fontSize: 11, color: "#7dd3fc" }}>
            Agentic Vision-Language Assistant for Remote Sensing · SIH26167
          </p>
        </div>
      </header>

      {/* Main layout */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "360px 1fr",
          gridTemplateRows: "1fr",
          height: "calc(100vh - 56px)",
          gap: 0,
        }}
      >
        {/* Left panel */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 16,
            padding: 16,
            overflowY: "auto",
            borderRight: "1px solid #e5e7eb",
            background: "#fff",
          }}
        >
          <section>
            <SectionHeader>Images</SectionHeader>
            <ImageUploadPanel images={images} onChange={setImages} />
          </section>

          <section>
            <SectionHeader>Query</SectionHeader>
            <QueryBar onSubmit={handleQuery} disabled={running} />
          </section>

          {globalError && (
            <p style={{ margin: 0, fontSize: 13, color: "#dc2626", background: "#fff1f2", padding: "8px 12px", borderRadius: 8 }}>
              {globalError}
            </p>
          )}

          <section>
            <SectionHeader>Results</SectionHeader>
            <ResultsPanel
              result={result}
              status={jobStatus?.status ?? (running ? "RUNNING" : "PENDING")}
              progressMessage={jobStatus?.progress_message ?? ""}
            />
          </section>
        </div>

        {/* Right panel — map */}
        <div style={{ padding: 16, background: "#f1f5f9" }}>
          <MapViewer evidence={result?.evidence ?? null} />
        </div>
      </div>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <p
      style={{
        margin: "0 0 8px",
        fontSize: 11,
        fontWeight: 700,
        color: "#6b7280",
        textTransform: "uppercase",
        letterSpacing: 1,
      }}
    >
      {children}
    </p>
  );
}
