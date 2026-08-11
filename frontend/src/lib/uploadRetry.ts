import axios, { AxiosError } from "axios";

const MAX_ATTEMPTS = 3;
const BASE_DELAY_MS = 1000;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** True only for transport-level failures (dropped connection, DNS, timeout) —
 * never for a real HTTP response (4xx/5xx), since retrying an expired or
 * rejected presigned URL just fails the same way again. */
function isRetryableNetworkError(err: unknown): boolean {
  if (!axios.isAxiosError(err)) return false;
  const axiosErr = err as AxiosError;
  return axiosErr.response === undefined;
}

/**
 * PUT a file to a presigned upload URL, retrying on transient network
 * failures (dropped connection, timeout) with exponential backoff.
 * A presigned URL is valid for its full expiry window, so re-sending the
 * same PUT on the same URL after a network blip is safe — unlike a real
 * rejection (expired URL, storage error), which surfaces immediately and
 * is not retried.
 */
export async function putFileWithRetry(
  url: string,
  file: File,
  onUploadProgress: (percent: number) => void
): Promise<void> {
  let lastError: unknown;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      await axios.put(url, file, {
        headers: { "Content-Type": file.type || "application/octet-stream" },
        onUploadProgress: (e) => {
          if (e.total) onUploadProgress(Math.round((e.loaded / e.total) * 100));
        },
      });
      return;
    } catch (err) {
      lastError = err;
      if (!isRetryableNetworkError(err) || attempt === MAX_ATTEMPTS) {
        throw err;
      }
      onUploadProgress(0);
      await sleep(BASE_DELAY_MS * 2 ** (attempt - 1));
    }
  }
  throw lastError;
}
