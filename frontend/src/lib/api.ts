export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";
export const getWorkspaceId = () => {
  if (typeof window === "undefined") return "";
  let id = window.localStorage.getItem("adi-workspace-id");
  if (!id) {
    id = window.crypto.randomUUID();
    window.localStorage.setItem("adi-workspace-id", id);
  }
  return id;
};

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (path !== "/api/health") headers.set("X-Workspace-Id", getWorkspaceId());
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store", signal: init.signal ?? AbortSignal.timeout(90000) });
  } catch {
    throw new Error("Couldn't reach the document service. Check that it is running and try again.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : "The request couldn't be completed. Check your input and try again.");
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export type DocumentItem = {
  id: string; filename: string; file_type: "pdf" | "txt"; status: string; created_at: string;
  chunks: number; size_bytes: number | null; collection_id: string | null;
};
export type Collection = { id: string; name: string; document_count: number };
export type Citation = { passage_id: string; document_id: string; filename: string; page_number: number; excerpt: string };
export type Passage = Omit<Citation, "excerpt"> & { text: string };
export type DocumentDetail = { document: DocumentItem; passages: Passage[] };
export type SearchResult = { mode: "local" | "generative"; answer: string | null; sources: Citation[] };
export type Health = { status: "ok"; ai_configured: boolean; provider_status: "not_configured" | "unverified" | "ready" | "error" };
