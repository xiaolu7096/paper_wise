import type { components } from "./generated";

export type Paper = components["schemas"]["Paper"];
export type PaperUploadResponse = components["schemas"]["PaperUploadResponse"];
export type Task = components["schemas"]["Task"];
export type RetryResponse = components["schemas"]["RetryResponse"];
export type SettingsStatus = components["schemas"]["SettingsStatus"];
export type SettingsUpdate = components["schemas"]["SettingsUpdate"];
export type Message = components["schemas"]["Message"];
export type ChatResponse = components["schemas"]["ChatResponse"];
export type ExplainTextRequest = components["schemas"]["ExplainTextRequest"];
export type ExplainTextResponse = components["schemas"]["ExplainTextResponse"];
export type ExplainRegionResponse = components["schemas"]["ExplainRegionResponse"];
export type Annotation = components["schemas"]["Annotation"];
export type AnnotationCreate = components["schemas"]["AnnotationCreate"];
export type CardResponse = components["schemas"]["CardResponse"];
export type AuthUser = components["schemas"]["AuthUser"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type RegisterRequest = components["schemas"]["RegisterRequest"];
type ErrorResponse = components["schemas"]["ErrorResponse"];

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");
export const AUTH_REQUIRED_EVENT = "paperwise:auth-required";

export class PaperwiseApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, body: ErrorResponse) {
    super(body.error.message);
    this.name = "PaperwiseApiError";
    this.status = status;
    this.code = body.error.code;
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }

  let body: ErrorResponse;
  try {
    body = (await response.json()) as ErrorResponse;
  } catch {
    body = {
      error: {
        code: "NETWORK_ERROR",
        message: `Request failed with status ${response.status}`,
        details: null,
      },
    };
  }
  if (
    body.error.code === "AUTH_REQUIRED"
    && !/\/auth(?:\/|$)/.test(response.url)
    && typeof window !== "undefined"
  ) {
    window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
  }
  throw new PaperwiseApiError(response.status, body);
}

function apiFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  return fetch(input, { credentials: "include", ...init });
}

export async function getCurrentUser(signal?: AbortSignal): Promise<AuthUser> {
  const response = await apiFetch(`${API_BASE_URL}/auth/me`, { signal });
  return parseResponse<AuthUser>(response);
}

export async function register(value: RegisterRequest): Promise<AuthUser> {
  const response = await apiFetch(`${API_BASE_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  });
  return parseResponse<AuthUser>(response);
}

export async function login(value: LoginRequest): Promise<AuthUser> {
  const response = await apiFetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  });
  return parseResponse<AuthUser>(response);
}

export async function logout(): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/auth/logout`, { method: "POST" });
  if (!response.ok) await parseResponse<never>(response);
}

export async function listPapers(signal?: AbortSignal): Promise<Paper[]> {
  const response = await apiFetch(`${API_BASE_URL}/papers`, { signal });
  const body = await parseResponse<components["schemas"]["PaperListResponse"]>(response);
  return body.items;
}

export async function getPaper(paperId: string, signal?: AbortSignal): Promise<Paper> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}`, {
    signal,
  });
  return parseResponse<Paper>(response);
}

export async function deletePaper(paperId: string): Promise<void> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}`, {
    method: "DELETE",
  });
  if (!response.ok) await parseResponse<never>(response);
}

export async function uploadPaper(file: File): Promise<PaperUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiFetch(`${API_BASE_URL}/papers`, {
    method: "POST",
    body: form,
  });
  return parseResponse<PaperUploadResponse>(response);
}

export async function getTask(taskId: string, signal?: AbortSignal): Promise<Task> {
  const response = await apiFetch(`${API_BASE_URL}/tasks/${encodeURIComponent(taskId)}`, {
    signal,
  });
  return parseResponse<Task>(response);
}

export async function retryPaper(paperId: string): Promise<RetryResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/retry`,
    { method: "POST" },
  );
  return parseResponse<RetryResponse>(response);
}

export function paperFileUrl(paperId: string): string {
  return `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/file`;
}

export async function getSettingsStatus(): Promise<SettingsStatus> {
  const response = await apiFetch(`${API_BASE_URL}/settings/status`);
  return parseResponse<SettingsStatus>(response);
}

export async function updateSettings(value: SettingsUpdate): Promise<SettingsStatus> {
  const response = await apiFetch(`${API_BASE_URL}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  });
  return parseResponse<SettingsStatus>(response);
}

export async function getMessages(paperId: string, signal?: AbortSignal): Promise<Message[]> {
  const response = await apiFetch(
    `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/messages`,
    { signal },
  );
  const body = await parseResponse<components["schemas"]["MessageListResponse"]>(response);
  return body.items;
}

export async function askPaper(paperId: string, question: string): Promise<ChatResponse> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  return parseResponse<ChatResponse>(response);
}

export async function clearMessages(paperId: string): Promise<void> {
  const response = await apiFetch(
    `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/messages`,
    { method: "DELETE" },
  );
  if (!response.ok) await parseResponse<never>(response);
}

export async function explainText(
  paperId: string,
  value: ExplainTextRequest,
): Promise<ExplainTextResponse> {
  const response = await apiFetch(
    `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/explain-text`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(value),
    },
  );
  return parseResponse<ExplainTextResponse>(response);
}

export async function explainRegion(
  paperId: string,
  value: {
    image: Blob;
    page: number;
    bbox: [number, number, number, number];
    viewportRotation: number;
    nearbyText: string;
    question: string;
  },
): Promise<ExplainRegionResponse> {
  const form = new FormData();
  form.append("image", value.image, "region.png");
  form.append("page", String(value.page));
  form.append("bbox", JSON.stringify(value.bbox));
  form.append("viewport_rotation", String(value.viewportRotation));
  form.append("nearby_text", value.nearbyText);
  form.append("question", value.question);
  const response = await apiFetch(
    `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/explain-region`,
    { method: "POST", body: form },
  );
  return parseResponse<ExplainRegionResponse>(response);
}

export function assetUrl(paperId: string, assetId: string): string {
  return `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/assets/${encodeURIComponent(assetId)}`;
}

export async function getAnnotations(paperId: string): Promise<Annotation[]> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/annotations`);
  const body = await parseResponse<components["schemas"]["AnnotationListResponse"]>(response);
  return body.items;
}

export async function createAnnotation(
  paperId: string,
  value: AnnotationCreate,
): Promise<Annotation> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/annotations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(value),
  });
  return parseResponse<Annotation>(response);
}

export async function deleteAnnotation(paperId: string, annotationId: string): Promise<void> {
  const response = await apiFetch(
    `${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/annotations/${encodeURIComponent(annotationId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) await parseResponse<never>(response);
}

export async function getCard(paperId: string): Promise<CardResponse> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/card`);
  return parseResponse<CardResponse>(response);
}

export async function generateCard(paperId: string, regenerate: boolean): Promise<CardResponse> {
  const response = await apiFetch(`${API_BASE_URL}/papers/${encodeURIComponent(paperId)}/card`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ regenerate }),
  });
  return parseResponse<CardResponse>(response);
}
