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
    <div className="upload-panel">
      {/* Drop zone */}
      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        className="drop-zone"
      >
        <div className="drop-icon">⌁</div>
        <p className="drop-title">
          Drop <strong>GeoTIFF / PNG / JPEG</strong> here or{" "}
          <span className="accent-text">browse</span>
        </p>
        <p className="drop-hint">
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
        <p className="upload-status">Uploading…</p>
      )}
      {error && (
        <p className="upload-error">{error}</p>
      )}

      {/* Uploaded image list */}
      {images.map((img) => (
        <div
          key={img.uploadId}
          className="file-card"
        >
          {img.previewUrl ? (
            <img
              src={img.previewUrl}
              alt={img.filename}
              className="file-preview"
            />
          ) : (
            <div
              className="file-preview file-type"
            >
              {img.format}
            </div>
          )}

          <div className="file-details">
            <p className="file-name">
              {img.filename}
            </p>
            <p className="file-meta">
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
            className="role-select"
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>

          <button
            onClick={() => onChange(images.filter((i) => i.uploadId !== img.uploadId))}
            className="remove-button"
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
