"""Fetch small, georeferenced Sentinel-2 crops for map-driven analysis.

Earth Search exposes Sentinel-2 COG assets through a public STAC API.  The
assets are read with GDAL range requests, so a map click only downloads the
small crop needed by the existing analysis pipeline.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from pyproj import Transformer

logger = logging.getLogger(__name__)


class ImageryUnavailable(RuntimeError):
    """Raised when public imagery cannot be found or read for a map location."""


def _asset_hrefs(assets: dict[str, Any]) -> tuple[list[str], bool]:
    """Return RGB hrefs and whether the source is a single RGB visual asset."""
    for names in (("red", "green", "blue"), ("B04", "B03", "B02")):
        hrefs = [
            asset.get("href") if isinstance(asset, dict) else None
            for asset in (assets.get(name) for name in names)
        ]
        if all(isinstance(href, str) for href in hrefs):
            return hrefs, False
    visual = assets.get("visual")
    if isinstance(visual, dict) and isinstance(visual.get("href"), str):
        return [visual["href"]], True
    raise ImageryUnavailable("The selected Sentinel-2 scene has no readable RGB assets.")


def _read_crop(
    hrefs: list[str],
    visual: bool,
    latitude: float,
    longitude: float,
    output_path: Path,
    tile_size: int,
) -> None:
    """Read one small COG window and write it as a local GeoTIFF."""
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
        with rasterio.open(hrefs[0]) as first:
            if not first.crs:
                raise ImageryUnavailable("The selected imagery has no coordinate reference system.")
            transformer = Transformer.from_crs("EPSG:4326", first.crs, always_xy=True)
            x, y = transformer.transform(longitude, latitude)
            bounds = first.bounds
            if not (bounds.left <= x <= bounds.right and bounds.bottom <= y <= bounds.top):
                raise ImageryUnavailable("The selected scene does not cover this map location.")

            half_width = max(first.res[0] * tile_size / 2, first.res[0])
            half_height = max(abs(first.res[1]) * tile_size / 2, abs(first.res[1]))
            crop_bounds = (
                max(bounds.left, x - half_width),
                max(bounds.bottom, y - half_height),
                min(bounds.right, x + half_width),
                min(bounds.top, y + half_height),
            )
            if crop_bounds[0] >= crop_bounds[2] or crop_bounds[1] >= crop_bounds[3]:
                raise ImageryUnavailable("The selected location is outside the imagery footprint.")

            window = from_bounds(*crop_bounds, transform=first.transform)
            output_transform = rasterio.transform.from_bounds(
                *crop_bounds, tile_size, tile_size
            )
            if visual:
                data = first.read(
                    indexes=[1, 2, 3] if first.count >= 3 else [1],
                    window=window,
                    out_shape=(min(first.count, 3), tile_size, tile_size),
                    boundless=True,
                    fill_value=0,
                )
                if data.shape[0] == 1:
                    data = data.repeat(3, axis=0)
                elif data.shape[0] == 2:
                    data = data[[0, 1, 0]]
            else:
                band_data = []
                for href in hrefs:
                    with rasterio.open(href) as band:
                        band_window = from_bounds(*crop_bounds, transform=band.transform)
                        band_data.append(
                            band.read(
                                1,
                                window=band_window,
                                out_shape=(tile_size, tile_size),
                                boundless=True,
                                fill_value=0,
                            )
                        )
                data = np.stack(band_data, axis=0)

            profile = first.profile.copy()
            profile.update(
                driver="GTiff",
                count=3,
                dtype="float32",
                width=tile_size,
                height=tile_size,
                transform=output_transform,
                compress="deflate",
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with rasterio.open(output_path, "w", **profile) as output:
                output.write(data[:3].astype("float32"))
                output.update_tags(
                    SATQUERY_SOURCE="Earth Search Sentinel-2 L2A",
                    SATQUERY_LATITUDE=str(latitude),
                    SATQUERY_LONGITUDE=str(longitude),
                )


async def fetch_sentinel_tile(
    latitude: float,
    longitude: float,
    output_path: Path,
    *,
    stac_url: str,
    collection: str,
    days_back: int,
    max_cloud_cover: float,
    tile_size: int,
) -> dict[str, Any]:
    """Find the clearest recent public Sentinel-2 scene and crop it around a point."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, days_back))
    payload = {
        "collections": [collection],
        "bbox": [
            max(-180.0, longitude - 0.05),
            max(-90.0, latitude - 0.05),
            min(180.0, longitude + 0.05),
            min(90.0, latitude + 0.05),
        ],
        "datetime": f"{start.isoformat()}/{end.isoformat()}",
        "limit": 20,
        "query": {"eo:cloud_cover": {"lte": max_cloud_cover}},
    }
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            response = await client.post(stac_url, json=payload)
            response.raise_for_status()
            features = response.json().get("features", [])
    except (httpx.HTTPError, ValueError, KeyError, AttributeError, TypeError) as exc:
        logger.warning("Public imagery search failed: %s", exc)
        raise ImageryUnavailable(
            "Public Sentinel-2 imagery is temporarily unavailable. "
            "Please try again or upload an image."
        ) from exc

    if not features:
        raise ImageryUnavailable(
            "No recent cloud-free Sentinel-2 scene covers this location. "
            "Try another location or upload an image."
        )

    def scene_key(feature: dict[str, Any]) -> tuple[float, str]:
        properties = feature.get("properties", {})
        cloud = properties.get("eo:cloud_cover", 100.0)
        return float(cloud) if isinstance(cloud, (int, float)) else 100.0, str(
            properties.get("datetime", "")
        )

    selected = min(features, key=scene_key)
    try:
        hrefs, visual = _asset_hrefs(selected["assets"])
        await asyncio.to_thread(
            _read_crop, hrefs, visual, latitude, longitude, output_path, tile_size
        )
    except ImageryUnavailable:
        raise
    except (
        OSError,
        rasterio.errors.RasterioIOError,
        ValueError,
        KeyError,
        AttributeError,
        TypeError,
    ) as exc:
        logger.warning("Public imagery asset read failed: %s", exc)
        raise ImageryUnavailable(
            "The public imagery asset could not be downloaded for this location. "
            "Please try again or upload an image."
        ) from exc

    return {
        "scene_id": selected.get("id"),
        "datetime": selected.get("properties", {}).get("datetime"),
        "cloud_cover": selected.get("properties", {}).get("eo:cloud_cover"),
    }
