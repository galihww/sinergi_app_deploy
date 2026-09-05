import { apiClient } from "@/lib/api";
import type { ChatMessage, ChatSession } from "@/lib/types";

type StoredMessagePayload = {
  id: string;
  role: "user" | "assistant";
  content: string;
  thinking?: string | null;
  thinking_seconds?: number | null;
  sources?: unknown[] | null;
  attachments?: StoredAttachmentPayload[] | null;
};

type StoredAttachmentPayload = {
  id: string;
  file_name: string;
  file_size: number;
  status: "done" | "error";
  token_count?: number | null;
  library_file_id?: string | null;
  page_count?: number | null;
  ocr_used?: boolean;
  warning?: string | null;
  error?: string | null;
};

type ChatPayload = {
  id?: string;
  title: string;
  messages: StoredMessagePayload[];
  is_pinned: boolean;
  model?: string | null;
  provider?: string | null;
  context_limit?: number | null;
  project_id?: string | null;
  created_at?: string;
  updated_at?: string;
};

function serializeMessage(message: ChatMessage): StoredMessagePayload {
  const payload: StoredMessagePayload = {
    id: message.id,
    role: message.role,
    content: message.content ?? "",
    thinking: message.thinking ?? null,
    thinking_seconds: message.thinkingSeconds ?? null,
    sources: message.sources ?? null,
    attachments:
      message.attachments?.map((attachment) => ({
        id: attachment.id,
        file_name: attachment.fileName,
        file_size: attachment.fileSize,
        status: attachment.status === "uploading" ? "error" : attachment.status,
        token_count: attachment.tokenCount ?? null,
        library_file_id: attachment.libraryFileId ?? null,
        page_count: attachment.pageCount ?? null,
        ocr_used: attachment.ocrUsed ?? false,
        warning: attachment.warning ?? null,
        error: attachment.error ?? null,
      })) ?? null,
  };
  return payload;
}

function normalizeMessage(payload: StoredMessagePayload): ChatMessage {
  return {
    id: payload.id,
    role: payload.role,
    content: payload.content,
    thinking: payload.thinking ?? undefined,
    thinkingSeconds: payload.thinking_seconds ?? undefined,
    sources: payload.sources as ChatMessage["sources"],
    attachments: payload.attachments?.map((attachment) => ({
      id: attachment.id,
      fileName: attachment.file_name,
      fileSize: attachment.file_size,
      status: attachment.status,
      tokenCount: attachment.token_count ?? undefined,
      libraryFileId: attachment.library_file_id ?? undefined,
      pageCount: attachment.page_count ?? undefined,
      ocrUsed: attachment.ocr_used ?? false,
      warning: attachment.warning ?? undefined,
      error: attachment.error ?? undefined,
    })),
  };
}

function normalizeSession(payload: ChatPayload): ChatSession {
  return {
    id: payload.id ?? "",
    title: payload.title ?? "",
    messages: (payload.messages ?? []).map(normalizeMessage),
    createdAt: payload.created_at ?? payload.updated_at ?? "",
    isPinned: Boolean(payload.is_pinned),
    model: (payload.model as ChatSession["model"]) ?? undefined,
    provider: (payload.provider as ChatSession["provider"]) ?? undefined,
    contextLimit: payload.context_limit ?? 128_000,
    projectId: payload.project_id ?? undefined,
  };
}

export function serializeSession(session: ChatSession): ChatPayload {
  return {
    id: session.id,
    title: session.title,
    messages: session.messages
      .filter((m) => !m.isLoading)
      .map(serializeMessage),
    is_pinned: Boolean(session.isPinned),
    model: session.model ?? null,
    provider: session.provider ?? null,
    context_limit: session.contextLimit ?? null,
    project_id: session.projectId ?? null,
  };
}

export async function listChatSessions(): Promise<ChatSession[]> {
  const response = await apiClient.get<{ chats: ChatPayload[] }>("/api/chats");
  return (response.data.chats ?? []).map(normalizeSession);
}

export async function getChatSession(id: string): Promise<ChatSession> {
  const response = await apiClient.get<ChatPayload>(`/api/chats/${id}`);
  return normalizeSession(response.data);
}

export async function saveChatSession(session: ChatSession): Promise<void> {
  await apiClient.post("/api/chats", serializeSession(session));
}

export async function deleteChatSession(id: string): Promise<void> {
  await apiClient.delete(`/api/chats/${id}`);
}
