"use client";

import { useState, useCallback } from "react";

/**
 * useCopyLink
 *
 * Copies a URL to the clipboard and briefly shows a "Copied!" confirmation.
 *
 * Returns:
 *  copy(url)  — call with the URL to copy
 *  copiedId   — the last URL that was copied (truthy for ~1.8s, then resets)
 */
export function useCopyLink() {
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const copy = useCallback((url: string) => {
    if (!url) return;
    navigator.clipboard
      .writeText(url)
      .then(() => {
        setCopiedId(url);
        setTimeout(() => setCopiedId(null), 1800);
      })
      .catch(() => {
        // Fallback for older browsers / insecure contexts
        try {
          const ta = document.createElement("textarea");
          ta.value = url;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
          setCopiedId(url);
          setTimeout(() => setCopiedId(null), 1800);
        } catch {
          // Silently ignore if all copy methods fail
        }
      });
  }, []);

  return { copy, copiedId };
}
