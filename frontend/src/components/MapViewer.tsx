import { useEffect, useRef } from "react";
import type { EvidenceObject } from "../types";

interface Props {
  evidence: EvidenceObject | null;
}

/**
 * Leaflet map viewer.
 * Displays georeferenced change maps and segmentation overlays
 * as image overlays when bbox_geo is available.
 * Falls back to a placeholder when no georeferenced data is present.
 */
export function MapViewer({ evidence }: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<unknown>(null);

  useEffect(() => {
    if (!mapRef.current) return;

    // Dynamically import Leaflet to avoid SSR issues
    import("leaflet").then((L) => {
      // Destroy existing map instance before re-initialising
      if (leafletMap.current) {
        (leafletMap.current as { remove: () => void }).remove();
        leafletMap.current = null;
      }

      const map = L.map(mapRef.current!, {
        center: [20.5937, 78.9629], // Default: India centre
        zoom: 5,
        zoomControl: true,
      });

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap contributors",
        maxZoom: 19,
      }).addTo(map);

      leafletMap.current = map;

      if (!evidence) return;

      // Fit map to first detected region with geo bbox
      const geoRegions = evidence.detected_regions.filter((r) => r.bbox_geo);
      if (geoRegions.length > 0) {
        const b = geoRegions[0].bbox_geo!;
        const bounds = L.latLngBounds(
          [b.miny, b.minx],
          [b.maxy, b.maxx],
        );
        map.fitBounds(bounds, { padding: [40, 40] });

        // Draw bounding box rectangles
        geoRegions.forEach((r) => {
          const rb = r.bbox_geo!;
          L.rectangle(
            [[rb.miny, rb.minx], [rb.maxy, rb.maxx]],
            { color: "#0ea5e9", weight: 2, fillOpacity: 0.15 },
          )
            .bindTooltip(`${r.label} (${(r.score * 100).toFixed(0)}%)`)
            .addTo(map);
        });
      }

      // Add change map / segmentation overlay as image overlay
      const overlayPath = evidence.change_map_path ?? evidence.overlay_path;
      if (overlayPath) {
        // Find a geo bbox from inputs (use first region or fallback)
        const anyBbox =
          geoRegions[0]?.bbox_geo ??
          (evidence.execution_plan?.query ? null : null);

        if (anyBbox) {
          const b = anyBbox;
          L.imageOverlay(
            `/results/${overlayPath.split(/[\\/]/).pop()}`,
            [[b.miny, b.minx], [b.maxy, b.maxx]],
            { opacity: 0.65 },
          ).addTo(map);
        }
      }
    });

    return () => {
      if (leafletMap.current) {
        (leafletMap.current as { remove: () => void }).remove();
        leafletMap.current = null;
      }
    };
  }, [evidence]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <div ref={mapRef} style={{ width: "100%", height: "100%", borderRadius: 10 }} />
      {!evidence && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(240,249,255,0.85)",
            borderRadius: 10,
            pointerEvents: "none",
          }}
        >
          <span style={{ fontSize: 36 }}>🛰️</span>
          <p style={{ margin: "8px 0 0", fontSize: 13, color: "#6b7280" }}>
            Georeferenced overlays will appear here after analysis
          </p>
        </div>
      )}
    </div>
  );
}
