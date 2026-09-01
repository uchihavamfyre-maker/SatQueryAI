import { useCallback, useState } from "react";
import { ImageUploadPanel } from "./components/ImageUploadPanel";
import { QueryBar } from "./components/QueryBar";
import { ResultsPanel } from "./components/ResultsPanel";
import { MapViewer } from "./components/MapViewer";
import { pollUntilDone, submitMapAnalysis, submitQuery } from "./api/client";
import type {
  InputRole,
  JobResultResponse,
  JobStatusResponse,
  UploadedImage,
} from "./types";
import { v4 as uuidv4 } from "./utils/uuid";

export default function App() {
  const [images, setImages] = useState<UploadedImage[]>([]);
  const [jobStatus, setJobStatus] = useState<JobStatusResponse | null>(null);
  const [result, setResult] = useState<JobResultResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedLocation, setSelectedLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);

  const runJob = useCallback(async (
    submit: (jobId: string) => Promise<JobStatusResponse>,
  ) => {
    setGlobalError(null);
    setResult(null);
    setRunning(true);

    const jobId = uuidv4();
    try {
      const initialStatus = await submit(jobId);
      setJobStatus(initialStatus);

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
  }, []);

  const handleQuery = (requestQuery: string) => {
    if (images.length === 0) {
      setGlobalError("Upload an image or click the map to use public Sentinel-2 imagery.");
      return;
    }
    const imageRoles: Record<string, InputRole> = {};
    images.forEach((img) => {
      imageRoles[img.uploadId] = img.role;
    });
    void runJob((jobId) =>
      submitQuery({ job_id: jobId, query: requestQuery, image_roles: imageRoles }),
    );
  };

  const handleMapClick = useCallback((latitude: number, longitude: number) => {
    if (running) return;
    const requestQuery = query.trim() || "What land cover type dominates this location?";
    setSelectedLocation({ latitude, longitude });
    void runJob((jobId) =>
      submitMapAnalysis({ job_id: jobId, query: requestQuery, latitude, longitude }),
    );
  }, [query, running, runJob]);

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
            <QueryBar
              onSubmit={handleQuery}
              disabled={running}
              value={query}
              onChange={setQuery}
            />
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
        <div style={{ minHeight: 0, height: "100%", padding: 16, background: "#f1f5f9" }}>
          <MapViewer
            evidence={result?.evidence ?? null}
            uploadedImages={images}
            onMapClick={handleMapClick}
            selectedLocation={selectedLocation}
            analysisPending={running}
          />
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
