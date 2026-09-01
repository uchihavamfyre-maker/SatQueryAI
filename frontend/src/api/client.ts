import axios from "axios";
import type {
  JobResultResponse,
  JobStatusResponse,
  QueryRequest,
  UploadResponse,
} from "../types";

const api = axios.create({ baseURL: "http://localhost:8000" });

export async function uploadImage(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<UploadResponse>("/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

export async function submitQuery(req: QueryRequest): Promise<JobStatusResponse> {
  const { data } = await api.post<JobStatusResponse>("/query", req);
  return data;
}

export async function getJobStatus(jobId: string): Promise<JobStatusResponse> {
  const { data } = await api.get<JobStatusResponse>(`/job/${jobId}/status`);
  return data;
}

export async function getJobResult(jobId: string): Promise<JobResultResponse> {
  const { data } = await api.get<JobResultResponse>(`/job/${jobId}/result`);
  return data;
}

export async function getJobTrace(jobId: string): Promise<unknown> {
  const { data } = await api.get(`/job/${jobId}/trace`);
  return data;
}

/** Poll job status until COMPLETED or FAILED, calling onProgress each tick. */
export async function pollUntilDone(
  jobId: string,
  onProgress: (status: JobStatusResponse) => void,
  intervalMs = 1500,
  timeoutMs = 300_000,
): Promise<JobResultResponse> {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    const tick = async () => {
      try {
        const status = await getJobStatus(jobId);
        onProgress(status);
        if (status.status === "COMPLETED" || status.status === "FAILED") {
          const result = await getJobResult(jobId);
          resolve(result);
          return;
        }
        if (Date.now() > deadline) {
          reject(new Error("Job timed out"));
          return;
        }
        setTimeout(tick, intervalMs);
      } catch (e) {
        reject(e);
      }
    };
    tick();
  });
}
