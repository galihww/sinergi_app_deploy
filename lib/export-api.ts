import { apiClient } from "@/lib/api";

export type ExportFormat = "docx" | "md";
export type ExportSourceType = "library_file" | "chat_message" | "chat_session";

export interface ExportRequest {
  source_type: ExportSourceType;
  source_id: string;
  message_id?: string;
  format: ExportFormat;
  include_sources?: boolean;
}

export function filenameFromContentDisposition(value?: string): string | null {
  if (!value) return null;
  const utf8 = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8?.[1]) {
    try {
      return decodeURIComponent(utf8[1].trim().replace(/^"|"$/g, ""));
    } catch {
      // Fall back to the ASCII filename below.
    }
  }
  const plain = value.match(/filename="?([^";]+)"?/i);
  return plain?.[1]?.trim() ?? null;
}

async function exportError(error: unknown): Promise<string> {
  const response = (error as { response?: { data?: unknown } })?.response;
  const data = response?.data;
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text()) as { detail?: string };
      if (parsed.detail) return parsed.detail;
    } catch {
      // Use the generic error below.
    }
  }
  return "Ekspor gagal. Silakan coba lagi.";
}

export async function downloadExport(payload: ExportRequest): Promise<string> {
  try {
    const response = await apiClient.post<Blob>("/api/exports", payload, {
      responseType: "blob",
    });
    const fallback = `legal-verse-export.${payload.format}`;
    const filename = filenameFromContentDisposition(response.headers["content-disposition"]) ?? fallback;
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1_000);
    return filename;
  } catch (error) {
    throw new Error(await exportError(error));
  }
}
