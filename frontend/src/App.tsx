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
    <div className="app-shell">
      {/* Header */}
      <header
        className="app-header"
      >
        <span className="brand-mark">✦</span>
        <div>
          <h1 className="brand-title">
            SatQuery AI
          </h1>
          <p className="brand-subtitle">
            Agentic Vision-Language Assistant for Remote Sensing · SIH26167
          </p>
        </div>
      </header>

      {/* Main layout */}
      <div
        className="workspace"
      >
        {/* Left panel */}
        <div
          className="control-panel"
        >
          <section className="panel-section">
            <SectionHeader>Images</SectionHeader>
            <ImageUploadPanel images={images} onChange={setImages} />
          </section>

          <section className="panel-section">
            <SectionHeader>Query</SectionHeader>
            <QueryBar
              onSubmit={handleQuery}
              disabled={running}
              value={query}
              onChange={setQuery}
            />
          </section>

          {globalError && (
            <p className="error-banner">
              {globalError}
            </p>
          )}

          <section className="panel-section results-section">
            <SectionHeader>Results</SectionHeader>
            <ResultsPanel
              result={result}
              status={jobStatus?.status ?? (running ? "RUNNING" : "PENDING")}
              progressMessage={jobStatus?.progress_message ?? ""}
            />
          </section>
        </div>

        {/* Right panel — map */}
        <div className="map-panel">
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
    <p className="section-header">
      {children}
    </p>
  );
}
