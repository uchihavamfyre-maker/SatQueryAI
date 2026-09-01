import React, { useCallback, useRef, useState } from "react";
import { uploadImage } from "../api/client";
import type { InputRole, UploadedImage } from "../types";

const ROLES: InputRole[] = ["PRIMARY", "T1", "T2", "OPTICAL", "SAR"];

interface Props {
  images: UploadedImage[];
  onChange: (images: UploadedImage[]) => void;
}

export function ImageUploadPanel({ images, onChange }: Props) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList) => {
      setError(null);
      setUploading(true);
      const newImages: UploadedImage[] = [];
      for (const file of Array.from(files)) {
        try {
          const resp = await uploadImage(file);
          const previewUrl = file.type.startsWith("image/")
            ? URL.createObjectURL(file)
            : null;
          const role = autoRole(resp.detected_modality, images.length + newImages.length);
          newImages.push({
            uploadId: resp.upload_id,
            filename: resp.filename,
            modality: resp.detected_modality,
            format: resp.detected_format,
            role,
            previewUrl,
            metadata: resp.quick_metadata,
          });
        } catch (e: unknown) {
          setError(`Failed to upload ${file.name}: ${(e as Error).message}`);
        }
      }
      onChange([...images, ...newImages]);
      setUploading(false);
    },
    [images, onChange],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {/* Drop zone */}
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        style={{
          border: "2px dashed #0ea5e9",
          borderRadius: 12,
          padding: "24px 16px",
          textAlign: "center",
          cursor: "pointer",
          background: "#f0f9ff",
        }}
      >
        <div style={{ fontSize: 28, marginBottom: 6 }}>📡</div>
        <p style={{ margin: 0, fontSize: 14, color: "#374151" }}>
          Drop <strong>GeoTIFF / PNG / JPEG</strong> here or{" "}
          <span style={{ color: "#0284c7" }}>browse</span>
        </p>
        <p style={{ margin: "4px 0 0", fontSize: 12, color: "#9ca3af" }}>
          GeoTIFF required for bi-temporal &amp; cross-modal tasks
        </p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".tif,.tiff,.png,.jpg,.jpeg"
          style={{ display: "none" }}
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
      </div>

      {uploading && (
        <p style={{ fontSize: 13, color: "#0284c7", margin: 0 }}>Uploading…</p>
      )}
      {error && (
        <p style={{ fontSize: 13, color: "#ef4444", margin: 0 }}>{error}</p>
      )}

      {/* Uploaded image list */}
      {images.map((img) => (
        <div
          key={img.uploadId}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            background: "#fff",
            border: "1px solid #e5e7eb",
            borderRadius: 8,
            padding: "10px 12px",
          }}
        >
          {img.previewUrl ? (
            <img
              src={img.previewUrl}
              alt={img.filename}
              style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 6 }}
            />
          ) : (
            <div
              style={{
                width: 48,
                height: 48,
                background: "#f3f4f6",
                borderRadius: 6,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 10,
                color: "#9ca3af",
              }}
            >
              {img.format}
            </div>
          )}

          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ margin: 0, fontSize: 13, fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {img.filename}
            </p>
            <p style={{ margin: 0, fontSize: 11, color: "#9ca3af" }}>
              {img.modality} · {img.format}
              {img.metadata.bands ? ` · ${img.metadata.bands as number} bands` : ""}
              {img.metadata.width
                ? ` · ${img.metadata.width as number}×${img.metadata.height as number}`
                : ""}
            </p>
          </div>

          <select
            value={img.role}
            onChange={(e) =>
              onChange(
                images.map((i) =>
                  i.uploadId === img.uploadId
                    ? { ...i, role: e.target.value as InputRole }
                    : i,
                ),
              )
            }
            style={{ fontSize: 12, border: "1px solid #d1d5db", borderRadius: 4, padding: "2px 4px" }}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>

          <button
            onClick={() => onChange(images.filter((i) => i.uploadId !== img.uploadId))}
            style={{ background: "none", border: "none", cursor: "pointer", color: "#9ca3af", fontSize: 18, lineHeight: 1 }}
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

function autoRole(modality: string, index: number): InputRole {
  if (modality === "SAR") return "SAR";
  if (index === 0) return "PRIMARY";
  if (index === 1) return "T2";
  return "PRIMARY";
}
