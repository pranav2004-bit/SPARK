"use client";

import { useState } from "react";

interface ImageLoaderProps {
  src: string;
  alt: string;
  /**
   * Hard cap on rendered height (px). The image never exceeds this, but the
   * container shrinks to the image's natural height — no dead space below.
   */
  maxHeight?: number;
  /** Background tint behind the image while it loads. */
  background?: string;
  /**
   * Height (px) of the shimmer placeholder shown while the image is in-flight.
   * Once the image loads the container collapses to the image's actual height.
   */
  skeletonHeight?: number;
}

/**
 * Global image renderer for question / explanation images.
 *
 * Loading UX:
 *   - Shimmer skeleton holds the space until the image is ready.
 *   - Image crossfades in once fully decoded — no sudden pop.
 *
 * Container UX:
 *   - The wrapper is sized by the image, not a fixed box.
 *   - max-width: 100%  → never overflows its column.
 *   - height: auto      → container exactly matches rendered image height.
 *   - max-height cap    → very tall images are constrained.
 *   Result: zero dead / hollow space around the image.
 */
export function ImageLoader({
  src,
  alt,
  maxHeight = 400,
  background = "#f8f9fa",
  skeletonHeight = 180,
}: ImageLoaderProps) {
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");

  if (status === "error") {
    return (
      <div
        className="flex items-center justify-center py-6 rounded-[var(--radius-md)]"
        style={{ background, border: "1px dashed var(--color-border)" }}
      >
        <p className="text-xs" style={{ color: "var(--color-text-subtle)" }}>
          Image could not be loaded.
        </p>
      </div>
    );
  }

  return (
    <div
      style={{
        position:  "relative",
        /* Reserve skeleton height only while loading; collapses after */
        minHeight: status === "loading" ? skeletonHeight : undefined,
      }}
    >
      {/* Shimmer skeleton — fills the reserved space while the image is in-flight */}
      {status === "loading" && (
        <div
          aria-hidden="true"
          style={{
            position:       "absolute",
            inset:          0,
            borderRadius:   "var(--radius-md)",
            background:     "linear-gradient(90deg, var(--color-border) 25%, var(--color-surface) 50%, var(--color-border) 75%)",
            backgroundSize: "200% 100%",
            animation:      "shimmer 1.4s infinite linear",
          }}
        />
      )}

      {/*
        Image sizing — dynamic, not fixed-box:
          max-width: 100%  → constrained to parent column width
          width: auto      → never upscales a narrow image
          height: auto     → container collapses to the image's natural height
          max-height       → hard cap for unusually tall images
        No object-contain needed — the image sizes itself naturally.
      */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={src}
        alt={alt}
        style={{
          display:    "block",
          maxWidth:   "100%",
          width:      "auto",
          height:     "auto",
          maxHeight,
          margin:     "0 auto",   /* centre narrow images within the column */
          background,
          opacity:    status === "loaded" ? 1 : 0,
          transition: "opacity 0.25s ease",
        }}
        onLoad={() => setStatus("loaded")}
        onError={() => setStatus("error")}
      />
    </div>
  );
}
