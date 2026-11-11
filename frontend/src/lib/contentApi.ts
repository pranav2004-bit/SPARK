import api from "@/lib/api";

// Typed client for the content bank (services/practice-service, /api/practice/content/).
// Mirrors LIVETRACKER4.md section 2.6. Draft writes carry If-Match (the ETag from the last read).

export type ContentStatus = "draft" | "published" | "retired";
export type VersionState = "draft" | "in_review" | "published";

export interface ContentNode {
  id: string;
  parent_id: string | null;
  name: string;
  display_order: number;
  status: ContentStatus;
  child_count: number;
  question_count: number;
}

export interface ContentOption {
  label: string;
  option_text: string;
  is_correct?: boolean;
  display_order: number;
}

export interface ContentVersion {
  version_no: number;
  state: VersionState;
  question_text: string;
  explanation: string;
  image_key: string;
  image_url: string;
  image_alt_text: string;
  options: ContentOption[];
}

export interface ContentQuestion {
  id: string;
  node_id: string;
  display_order: number;
  status: ContentStatus;
  current_version_no: number;
  published_version_no: number | null;
  editable_version: ContentVersion | null;
}

export interface ContentPage<T> {
  count: number;
  total_pages: number;
  current_page: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export class ContentApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly errors: Record<string, string[]>;
  readonly requestId: string | null;

  constructor(message: string, code: string, status: number, errors: Record<string, string[]>, requestId: string | null = null) {
    super(message);
    this.name = "ContentApiError";
    this.code = code;
    this.status = status;
    this.errors = errors;
    this.requestId = requestId;
  }
}

interface Envelope<T> {
  success: boolean;
  message?: string;
  data?: T;
}

interface Result<T> {
  data: T;
  etag: string | null;
}

function toApiError(err: unknown): ContentApiError {
  const e = err as {
    response?: { status?: number; data?: { message?: string; code?: string; errors?: unknown; request_id?: string } };
    message?: string;
  };
  const status = e.response?.status ?? 0;
  const body = e.response?.data;
  const rawErrors = body?.errors;
  const errors: Record<string, string[]> =
    rawErrors && typeof rawErrors === "object" && !Array.isArray(rawErrors)
      ? Object.fromEntries(
          Object.entries(rawErrors as Record<string, unknown>).map(([k, v]) => [
            k,
            Array.isArray(v) ? v.map(String) : [String(v)],
          ]),
        )
      : {};
  return new ContentApiError(
    body?.message ?? e.message ?? "Request failed.",
    body?.code ?? (status === 0 ? "network_error" : "unknown_error"),
    status,
    errors,
    typeof body?.request_id === "string" && body.request_id ? body.request_id : null,
  );
}

async function run<T>(request: Promise<{ data: Envelope<T> | T; headers: Record<string, string> }>): Promise<Result<T>> {
  try {
    const res = await request;
    const body = res.data as Envelope<T>;
    const data = (body && typeof body === "object" && "data" in body ? body.data : res.data) as T;
    return { data, etag: res.headers?.etag ?? null };
  } catch (err) {
    throw toApiError(err);
  }
}

const BASE = "/practice/content";

function ifMatch(etag: string | null | undefined) {
  return etag ? { headers: { "If-Match": etag } } : {};
}

export const contentApi = {
  listNodes: (parentId: string | null, page = 1) =>
    run<ContentPage<ContentNode>>(
      api.get(`${BASE}/nodes/?parent_id=${parentId ?? "null"}&page=${page}`) as never,
    ),
  getNode: (id: string) => run<ContentNode>(api.get(`${BASE}/nodes/${id}/`) as never),
  createNode: (name: string, parentId: string | null) =>
    run<ContentNode>(api.post(`${BASE}/nodes/`, { name, parent_id: parentId }) as never),
  renameNode: (id: string, name: string) =>
    run<ContentNode>(api.patch(`${BASE}/nodes/${id}/`, { name }) as never),
  nodeAction: (id: string, action: "publish" | "retire" | "restore") =>
    run<ContentNode>(api.post(`${BASE}/nodes/${id}/${action}/`) as never),
  deleteNode: (id: string) => run<null>(api.delete(`${BASE}/nodes/${id}/`) as never),
  reorderNodes: (parentId: string | null, nodeIds: string[]) =>
    run<null>(api.post(`${BASE}/nodes/reorder/`, { parent_id: parentId, node_ids: nodeIds }) as never),

  listQuestions: (nodeId: string, page = 1) =>
    run<ContentPage<ContentQuestion>>(
      api.get(`${BASE}/questions/?node_id=${nodeId}&page=${page}`) as never,
    ),
  getQuestion: (id: string) => run<ContentQuestion>(api.get(`${BASE}/questions/${id}/`) as never),
  createQuestion: (nodeId: string, text: string, options: ContentOption[], explanation: string) =>
    run<ContentQuestion>(
      api.post(`${BASE}/questions/`, { node_id: nodeId, text, options, explanation }) as never,
    ),
  saveDraft: (id: string, body: { text?: string; explanation?: string; options?: ContentOption[] }, etag: string | null) =>
    run<ContentQuestion>(api.patch(`${BASE}/questions/${id}/`, body, ifMatch(etag)) as never),
  questionAction: (
    id: string,
    action: "submit-review" | "withdraw-review" | "publish" | "retire" | "restore" | "discard-draft",
    etag: string | null,
  ) => run<ContentQuestion>(api.post(`${BASE}/questions/${id}/${action}/`, {}, ifMatch(etag)) as never),
  deleteQuestion: (id: string) => run<null>(api.delete(`${BASE}/questions/${id}/`) as never),
  reorderQuestions: (nodeId: string, questionIds: string[]) =>
    run<null>(api.post(`${BASE}/questions/reorder/`, { node_id: nodeId, question_ids: questionIds }) as never),
  listVersions: (id: string) =>
    run<{ version_no: number; state: VersionState; published_at: string | null }[]>(
      api.get(`${BASE}/questions/${id}/versions/`) as never,
    ),
  getVersion: (id: string, versionNo: number) =>
    run<ContentVersion>(api.get(`${BASE}/questions/${id}/versions/${versionNo}/`) as never),
  presignImage: (id: string, filename: string, contentType: string, etag: string | null) =>
    run<{ upload_url: string; file_key: string; method: string }>(
      api.post(`${BASE}/questions/${id}/image/presign/`, { filename, content_type: contentType }, ifMatch(etag)) as never,
    ),
  confirmImage: (id: string, fileKey: string, altText: string, etag: string | null) =>
    run<ContentQuestion>(
      api.post(`${BASE}/questions/${id}/image/confirm/`, { file_key: fileKey, image_alt_text: altText }, ifMatch(etag)) as never,
    ),
  removeImage: (id: string, etag: string | null) =>
    run<ContentQuestion>(api.delete(`${BASE}/questions/${id}/image/`, ifMatch(etag)) as never),
};

// User-facing status words. The API still uses "retired"; the screens call it "Unpublished".
export const STATUS_TEXT: Record<ContentStatus, string> = {
  draft: "Draft",
  published: "Published",
  retired: "Unpublished",
};

export const CONTENT_ERROR_MESSAGES: Record<string, string> = {
  duplicate_name: "This name is already used here. Choose a different name.",
  node_not_empty: "This still has topics or questions. Remove or move them first, then try again.",
  node_retired: "This is unpublished, so you can't add to it. Publish it first.",
  invalid_parent: "Questions must go inside a topic, not directly under a subject.",
  used_question: "This question was used in an exam, so it can only be unpublished, not deleted.",
  stale_version: "This question changed since you opened it. Reload to see the latest version.",
  precondition_required: "Reload the page and try again.",
  invalid_transition: "This action isn't available for the current status.",
  storage_unavailable: "File storage is temporarily unavailable. Try again shortly.",
  image_rejected: "This image could not be used. Check the file and try again.",
  image_type_unsupported: "Only JPEG, PNG, WebP, GIF, or AVIF images are allowed.",
  image_too_large: "Images must be 5 MB or smaller.",
  dependency_unavailable: "The service is temporarily unavailable. Please try again.",
  set_mismatch: "The list changed. Reload and try again.",
};

export function messageFor(err: unknown): string {
  if (err instanceof ContentApiError) {
    const first = Object.values(err.errors)[0]?.[0];
    const text = CONTENT_ERROR_MESSAGES[err.code] ?? first ?? err.message;
    // Only server-side failures show a reference, so support can find the request in the logs.
    // Validation and business-rule messages are shown on their own.
    return err.status >= 500 && err.requestId ? `${text} (Reference: ${err.requestId})` : text;
  }
  return "Something went wrong. Please try again.";
}
