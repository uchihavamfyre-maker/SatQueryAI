"""Dependency-light remote-sensing baselines used when heavyweight checkpoints are unavailable.
These are real image-analysis algorithms, not fake/stub outputs. They are explicitly
reported as BASELINE so a demo never pretends an untrained checkpoint is a trained model.
"""
from __future__ import annotations
import re
import numpy as np
import cv2

CLASSES = ["built_up", "water", "vegetation", "bare_soil", "other"]


def robust01(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, np.float32)
    out = np.empty_like(x)
    for i in range(x.shape[0]):
        b = x[i]
        lo, hi = np.percentile(b[np.isfinite(b)], [2, 98]) if np.isfinite(b).any() else (0, 1)
        out[i] = np.clip((b - lo) / max(float(hi - lo), 1e-6), 0, 1)
    return out


def rgb_from_chw(x: np.ndarray) -> np.ndarray:
    x = robust01(x)
    if x.shape[0] == 1:
        rgb = np.repeat(x, 3, axis=0)
    elif x.shape[0] == 2:
        rgb = np.stack([x[0], x[1], x[0]], axis=0)
    elif x.shape[0] == 3:
        rgb = x
    else:
        # Sentinel-2 common B,G,R,NIR ordering -> R,G,B
        rgb = x[[3, 2, 1]]
    return np.transpose(rgb, (1, 2, 0)).astype(np.float32)


def image_stats(x: np.ndarray) -> dict:
    rgb = rgb_from_chw(x)
    hsv = cv2.cvtColor((rgb * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
    green = rgb[..., 1]
    red = rgb[..., 0]
    blue = rgb[..., 2]
    return {
        "green_fraction": float(np.mean((green > red * 1.08) & (green > blue * 0.95))),
        "water_fraction": float(np.mean((blue > red * 1.12) & (blue > green * 1.02) & (hsv[..., 1] > 35))),
        "bright_fraction": float(np.mean(np.mean(rgb, axis=2) > 0.72)),
        "dark_fraction": float(np.mean(np.mean(rgb, axis=2) < 0.22)),
        "mean_rgb": [float(v) for v in rgb.mean(axis=(0, 1))],
    }


def scene_caption(x: np.ndarray) -> str:
    s = image_stats(x)
    labels = []
    if s["water_fraction"] > 0.12: labels.append("water")
    if s["green_fraction"] > 0.18: labels.append("vegetation")
    if s["bright_fraction"] > 0.25: labels.append("bright/open or built surfaces")
    if not labels: labels.append("mixed land cover")
    return ("The satellite scene appears to contain " + ", ".join(labels) + ". "
            f"Estimated vegetation fraction is {s['green_fraction']:.1%} and water fraction is {s['water_fraction']:.1%}. "
            "This result is produced by a transparent image-analysis baseline when the trained VLM is unavailable.")


def answer_vqa(x: np.ndarray, question: str) -> tuple[str, float]:
    q = question.lower()
    s = image_stats(x)
    if any(k in q for k in ["water", "river", "lake"]):
        return (f"Yes — water-like pixels are estimated at {s['water_fraction']:.1%} of the scene." if s["water_fraction"] > .03
                else "No clear water-like region is detected by the baseline.", min(.95, .55 + s["water_fraction"]))
    if any(k in q for k in ["vegetation", "forest", "green", "crop"]):
        return (f"Vegetation-like cover is estimated at {s['green_fraction']:.1%} of the scene.", min(.95, .55 + s["green_fraction"]))
    if any(k in q for k in ["land cover", "dominant", "main class"]):
        vals = {"vegetation": s["green_fraction"], "water": s["water_fraction"], "built/open": max(0.0, 1-s["green_fraction"]-s["water_fraction"])}
        k = max(vals, key=vals.get)
        return f"The dominant broad land-cover signal is {k} ({vals[k]:.1%}).", min(.9, .55 + vals[k])
    if any(k in q for k in ["bright", "built", "urban", "city"]):
        return f"Bright/built-like surfaces occupy approximately {s['bright_fraction']:.1%} of the scene.", min(.9, .55+s["bright_fraction"])
    return scene_caption(x), .55


def change_mask(t1: np.ndarray, t2: np.ndarray, threshold: float=.5) -> tuple[np.ndarray, np.ndarray, float]:
    a, b = rgb_from_chw(t1), rgb_from_chw(t2)
    a = cv2.GaussianBlur(a, (5,5), 0)
    b = cv2.GaussianBlur(b, (5,5), 0)
    diff = np.mean(np.abs(a-b), axis=2)
    # Adaptive thresholding is more robust to seasonal illumination differences than raw 0.5.
    p85 = float(np.percentile(diff, 85)); p95 = float(np.percentile(diff, 95))
    cut = max(0.08, min(0.5, p85 * (0.75 + threshold*0.25)))
    mask = (diff >= cut).astype(np.uint8)
    kernel = np.ones((5,5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9,9), np.uint8))
    # Remove tiny components.
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    min_area = max(16, int(mask.size * 0.0002))
    clean = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area: clean[lab == i] = 1
    prob = np.clip((diff - cut) / max(p95-cut, 1e-6), 0, 1).astype(np.float32)
    ratio = float(clean.mean())
    confidence = float(np.mean(prob[clean==1])) if clean.any() else float(max(0.55, 1-np.mean(diff)))
    return clean, prob, min(.95, max(.5, confidence))


def change_caption(t1: np.ndarray, t2: np.ndarray, mask: np.ndarray|None=None) -> tuple[str,float]:
    if mask is None: mask, _, conf = change_mask(t1,t2)
    ratio = float(mask.mean())
    if ratio < .01: text = "No substantial spatial change is detected; differences are below the baseline's change threshold."
    elif ratio < .10: text = f"Localized change is detected across approximately {ratio:.1%} of the image area."
    else: text = f"Extensive change is detected across approximately {ratio:.1%} of the image area."
    return text + " The change map highlights the affected pixels.", conf


def change_vqa(t1: np.ndarray, t2: np.ndarray, question: str, mask: np.ndarray|None=None) -> tuple[str,float]:
    if mask is None: mask, _, conf = change_mask(t1,t2)
    ratio = float(mask.mean()); q=question.lower()
    if any(k in q for k in ["how much", "percentage", "percent", "area"]):
        return f"Approximately {ratio:.1%} of the aligned image shows detected change.", conf
    if any(k in q for k in ["did", "changed", "change", "different"]):
        return ("Yes, spatial change is detected." if ratio >= .01 else "No substantial spatial change is detected."), conf
    return change_caption(t1,t2,mask)


def multisource_segmentation(optical: np.ndarray, sar: np.ndarray) -> tuple[np.ndarray,np.ndarray,dict[str,float]]:
    rgb = rgb_from_chw(optical)
    hsv = cv2.cvtColor((rgb*255).astype(np.uint8), cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[...,1]/255.; val=hsv[...,2]/255.
    green = rgb[...,1]; red=rgb[...,0]; blue=rgb[...,2]
    sar01 = robust01(sar).mean(axis=0)
    m = np.zeros(rgb.shape[:2], np.int32)
    water = (blue > red*1.12) & (blue > green*1.02) & (sat>.12)
    veg = (green > red*1.05) & (green > blue*.95) & (sat>.15)
    built = (val>.55) & (sat<.45)
    bare = (val>.35) & (sat<.35) & ~veg & ~water
    # SAR backscatter refines built/open separation: high backscatter often indicates structures/rough surfaces.
    built |= (sar01 > np.percentile(sar01, 72)) & ~water
    m[water]=1; m[veg]=2; m[bare]=3; m[built]=0
    probs = np.full((5,*m.shape), .05, np.float32)
    scores=[built.astype(float), water.astype(float), veg.astype(float), bare.astype(float), np.ones_like(sat)*.15]
    stack=np.stack(scores,axis=0); stack += .05
    probs = (stack/np.sum(stack,axis=0,keepdims=True)).astype(np.float32)
    m=np.argmax(probs,axis=0).astype(np.int32)
    areas={CLASSES[i]: float(np.mean(m==i)) for i in range(5)}
    conf=float(np.mean(np.max(probs,axis=0)))
    return m, probs, areas, conf


def grounding(rgb_chw: np.ndarray, query: str) -> list[dict]:
    rgb = rgb_from_chw(rgb_chw)
    q=query.lower()
    h,w=rgb.shape[:2]
    if any(k in q for k in ["water","river","lake"]):
        mask=(rgb[...,2]>rgb[...,0]*1.12)&(rgb[...,2]>rgb[...,1]*1.02)
    elif any(k in q for k in ["vegetation","forest","tree","crop","green"]):
        mask=(rgb[...,1]>rgb[...,0]*1.05)&(rgb[...,1]>rgb[...,2]*.95)
    elif any(k in q for k in ["building","built","urban","road","city"]):
        g=np.mean(rgb,axis=2); mask=(g>.55)&(np.max(rgb,axis=2)-np.min(rgb,axis=2)<.3)
    else:
        gray=cv2.cvtColor((rgb*255).astype(np.uint8),cv2.COLOR_RGB2GRAY); mask=gray>np.percentile(gray,65)
    mask=(mask.astype(np.uint8)*255)
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    n,lab,stats,_=cv2.connectedComponentsWithStats(mask,8)
    out=[]
    for i in range(1,n):
        x,y,ww,hh,area=stats[i]
        if area < max(25,0.002*h*w): continue
        score=min(.95,.5+area/(h*w))
        out.append({"x1":float(x),"y1":float(y),"x2":float(x+ww),"y2":float(y+hh),"score":score,"label":query[:80]})
    return sorted(out,key=lambda z:z["score"],reverse=True)[:5]
