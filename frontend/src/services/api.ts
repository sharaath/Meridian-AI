import { Platform } from 'react-native';
import {
  AdminOverview,
  AIModelInfo,
  AssistantMode,
  AuthResponse,
  Citation,
  Conversation,
  ConversationDetail,
  MemoryItem,
  Message,
  ProjectItem,
  ProviderStatus,
  UploadedFile,
  UsageStats,
  UserPreferences,
  UserSummary,
} from '@/types/api';

function resolveApiBaseUrl(): string {
  const configured = (process.env.EXPO_PUBLIC_API_URL || '').trim().replace(/\/$/, '');
  if (Platform.OS === 'web' && typeof window !== 'undefined') {
    const host = window.location.hostname;
    const isLocalHost = host === 'localhost' || host === '127.0.0.1';
    if (!isLocalHost && (!configured || configured.includes('localhost') || configured.includes('127.0.0.1'))) {
      return `http://${host}:8000`;
    }
  }
  return configured || 'http://localhost:8000';
}

const BASE_URL = resolveApiBaseUrl();

let authToken: string | null = null;

export function setApiToken(token: string | null) {
  authToken = token;
}

export function getApiBaseUrl() {
  return BASE_URL;
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    ...(init.headers as Record<string, string> | undefined),
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }
  if (!(init.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (res.status === 204) {
    return undefined as unknown as T;
  }

  const text = await res.text();
  let json: any = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    json = null;
  }

  if (!res.ok) {
    const detail = json?.detail || text || `Request failed (${res.status})`;
    throw new ApiError(res.status, typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return json as T;
}

export interface StreamCallbacks {
  onMeta?: (meta: {
    conversation_id: string;
    conversation_title: string;
    user_message_id: string;
    model_id: string;
    citations: Citation[];
  }) => void;
  onDelta?: (deltaText: string) => void;
  onDone?: (payload: {
    conversation_id: string;
    assistant_message: Message;
    follow_ups: string[];
    usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  }) => void;
  onError?: (detail: string) => void;
}

function parseSseBuffer(buffer: string, callbacks: StreamCallbacks): string {
  const blocks = buffer.split('\n\n');
  const remainder = blocks.pop() || '';
  for (const block of blocks) {
    if (!block.trim()) continue;
    let eventName = 'message';
    let dataLine = '';
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) {
        eventName = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataLine += line.slice(6);
      }
    }
    if (!dataLine) continue;
    try {
      const data = JSON.parse(dataLine);
      if (eventName === 'meta') callbacks.onMeta?.(data);
      else if (eventName === 'delta') callbacks.onDelta?.(data.text || '');
      else if (eventName === 'done') callbacks.onDone?.(data);
      else if (eventName === 'error') callbacks.onError?.(data.detail || 'Stream error');
    } catch {
      // Ignore partial JSON frames
    }
  }
  return remainder;
}

async function streamSsePost(
  path: string,
  body: Record<string, unknown>,
  callbacks: StreamCallbacks,
  signal?: AbortSignal
): Promise<void> {
  // Web & environments supporting ReadableStream on fetch
  if (Platform.OS === 'web' || typeof ReadableStream !== 'undefined') {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });

    if (!res.ok) {
      const errText = await res.text();
      let detail = errText;
      try {
        detail = JSON.parse(errText)?.detail || errText;
      } catch {}
      throw new ApiError(res.status, detail || `Stream failed (${res.status})`);
    }

    if (res.body && typeof res.body.getReader === 'function') {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = parseSseBuffer(buffer, callbacks);
      }
      if (buffer.trim()) {
        parseSseBuffer(buffer + '\n\n', callbacks);
      }
      return;
    }

    // Fallback if response body has no ReadableStream
    const fullText = await res.text();
    parseSseBuffer(fullText + '\n\n', callbacks);
    return;
  }

  // React Native native progressive XHR fallback
  await new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE_URL}${path}`);
    xhr.setRequestHeader('Content-Type', 'application/json');
    if (authToken) xhr.setRequestHeader('Authorization', `Bearer ${authToken}`);

    let seenIndex = 0;
    let buffer = '';

    const onAbort = () => {
      xhr.abort();
      reject(new DOMException('Aborted', 'AbortError'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });

    xhr.onprogress = () => {
      const chunk = xhr.responseText.slice(seenIndex);
      seenIndex = xhr.responseText.length;
      if (chunk) {
        buffer += chunk;
        buffer = parseSseBuffer(buffer, callbacks);
      }
    };

    xhr.onload = () => {
      signal?.removeEventListener('abort', onAbort);
      if (xhr.status >= 400) {
        let detail = xhr.responseText;
        try {
          detail = JSON.parse(xhr.responseText)?.detail || xhr.responseText;
        } catch {}
        reject(new ApiError(xhr.status, detail));
        return;
      }
      const tail = xhr.responseText.slice(seenIndex);
      if (tail) buffer += tail;
      if (buffer.trim()) parseSseBuffer(buffer + '\n\n', callbacks);
      resolve();
    };

    xhr.onerror = () => {
      signal?.removeEventListener('abort', onAbort);
      reject(new Error('Network error while streaming response.'));
    };

    xhr.send(JSON.stringify(body));
  });
}

export const api = {
  health: () => request<{ status: string; configured_models: number; auth_mode: string; database: string }>('/api/health'),

  // Auth
  register: (email: string, username: string, password: string) =>
    request<AuthResponse>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, username, password }),
    }),
  login: (email: string, password: string) =>
    request<AuthResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: () => request<{ status: string }>('/api/auth/logout', { method: 'POST' }),
  me: () => request<UserSummary>('/api/auth/me'),
  requestEmailVerification: () =>
    request<{ status: string; dev_verification_token?: string }>('/api/auth/verify-email/request', { method: 'POST' }),
  confirmEmailVerification: (token: string) =>
    request<{ status: string }>('/api/auth/verify-email/confirm', {
      method: 'POST',
      body: JSON.stringify({ token }),
    }),
  requestPasswordReset: (email: string) =>
    request<{ status: string; message: string; dev_reset_token?: string }>('/api/auth/password-reset/request', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),
  confirmPasswordReset: (token: string, new_password: string) =>
    request<{ status: string }>('/api/auth/password-reset/confirm', {
      method: 'POST',
      body: JSON.stringify({ token, new_password }),
    }),
  googleOAuthUrl: (redirectTo: string) =>
    request<{ url: string }>(`/api/auth/oauth/google?redirect_to=${encodeURIComponent(redirectTo)}`),

  // Models
  listModels: () => request<{ models: AIModelInfo[]; default_model: string | null; any_configured: boolean }>('/api/models'),
  listModelCatalog: () => request<{ models: AIModelInfo[]; providers: ProviderStatus[] }>('/api/models/catalog'),

  // Conversations & Streaming Chat
  listConversations: (q?: string, projectId?: string) => {
    const params = new URLSearchParams();
    if (q) params.set('q', q);
    if (projectId) params.set('project_id', projectId);
    const qs = params.toString();
    return request<Conversation[]>(`/api/conversations${qs ? `?${qs}` : ''}`);
  },
  createConversation: (payload: { title?: string; project_id?: string | null; model_id?: string; mode?: AssistantMode }) =>
    request<Conversation>('/api/conversations', { method: 'POST', body: JSON.stringify(payload) }),
  getConversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  updateConversation: (id: string, payload: Partial<Pick<Conversation, 'title' | 'project_id' | 'model_id' | 'mode' | 'is_pinned'>>) =>
    request<Conversation>(`/api/conversations/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteConversation: (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),

  streamChat: (
    payload: {
      conversation_id?: string | null;
      project_id?: string | null;
      content: string;
      model_id?: string | null;
      mode?: AssistantMode;
      attachment_ids?: string[];
      use_web_search?: boolean;
    },
    callbacks: StreamCallbacks,
    signal?: AbortSignal
  ) => streamSsePost('/api/chat/stream', payload, callbacks, signal),

  editAndResend: (
    messageId: string,
    payload: { content: string; model_id?: string | null; use_web_search?: boolean },
    callbacks: StreamCallbacks,
    signal?: AbortSignal
  ) => streamSsePost(`/api/chat/messages/${messageId}/edit`, payload, callbacks, signal),

  regenerateResponse: (
    conversationId: string,
    payload: { model_id?: string | null; use_web_search?: boolean },
    callbacks: StreamCallbacks,
    signal?: AbortSignal
  ) => streamSsePost(`/api/chat/conversations/${conversationId}/regenerate`, payload, callbacks, signal),

  exportConversationUrl: (conversationId: string, format: 'txt' | 'pdf') =>
    `${BASE_URL}/api/conversations/${conversationId}/export?format=${format}`,
  exportMessageUrl: (messageId: string, format: 'txt' | 'pdf' | 'docx' | 'pptx' = 'pdf') =>
    `${BASE_URL}/api/messages/${messageId}/export?format=${format}`,
  downloadExportText: async (conversationId: string, format: 'txt' | 'pdf'): Promise<Blob> => {
    const res = await fetch(`${BASE_URL}/api/conversations/${conversationId}/export?format=${format}`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => null);
      throw new ApiError(res.status, errJson?.detail || `Export failed (${res.status})`);
    }
    return res.blob();
  },
  downloadMessageExport: async (messageId: string, format: 'txt' | 'pdf' | 'docx' | 'pptx' = 'pdf'): Promise<Blob> => {
    const res = await fetch(`${BASE_URL}/api/messages/${messageId}/export?format=${format}`, {
      headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => null);
      throw new ApiError(res.status, errJson?.detail || `Export failed (${res.status})`);
    }
    return res.blob();
  },

  shareConversation: (conversationId: string) =>
    request<{ share_token: string; conversation_id: string }>(`/api/conversations/${conversationId}/share`, {
      method: 'POST',
    }),
  revokeShare: (conversationId: string) =>
    request<void>(`/api/conversations/${conversationId}/share`, { method: 'DELETE' }),
  viewShared: (token: string) =>
    request<{ title: string; mode: string; created_at: string; messages: Message[] }>(`/api/shared/${token}`),

  // Files & Document Intelligence
  uploadFile: async (file: { uri: string; name: string; type: string; webFile?: File }, conversationId?: string) => {
    const form = new FormData();
    if (file.webFile) {
      form.append('file', file.webFile);
    } else {
      form.append('file', { uri: file.uri, name: file.name, type: file.type } as unknown as Blob);
    }
    if (conversationId) form.append('conversation_id', conversationId);
    return request<UploadedFile>('/api/files/upload', { method: 'POST', body: form });
  },
  listFiles: (fileType?: string) =>
    request<UploadedFile[]>(`/api/files${fileType ? `?file_type=${fileType}` : ''}`),
  getFileDetail: (fileId: string) => request<UploadedFile>(`/api/files/${fileId}`),
  deleteFile: (fileId: string) => request<void>(`/api/files/${fileId}`, { method: 'DELETE' }),
  analyzeDocuments: (fileIds: string[], question: string, modelId?: string | null) =>
    request<{ answer: string; model_id: string; references: Array<{ file_id: string; filename: string; page_count: number }> }>(
      '/api/files/analyze',
      {
        method: 'POST',
        body: JSON.stringify({ file_ids: fileIds, question, model_id: modelId }),
      }
    ),

  // Voice transcription
  transcribeAudio: async (uri: string, mimeType = 'audio/m4a', webBlob?: Blob) => {
    const form = new FormData();
    if (webBlob) {
      form.append('file', webBlob, 'recording.webm');
    } else {
      form.append('file', { uri, name: 'recording.m4a', type: mimeType } as unknown as Blob);
    }
    return request<{ transcript: string; model_id: string }>('/api/voice/transcribe', {
      method: 'POST',
      body: form,
    });
  },

  // Memories
  listMemories: () => request<MemoryItem[]>('/api/memories'),
  createMemory: (memory_content: string, category = 'general') =>
    request<MemoryItem>('/api/memories', { method: 'POST', body: JSON.stringify({ memory_content, category }) }),
  updateMemory: (id: string, payload: { memory_content?: string; category?: string }) =>
    request<MemoryItem>(`/api/memories/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteMemory: (id: string) => request<void>(`/api/memories/${id}`, { method: 'DELETE' }),

  // Projects
  listProjects: () => request<ProjectItem[]>('/api/projects'),
  createProject: (payload: { name: string; description?: string; custom_instructions?: string; color?: string }) =>
    request<ProjectItem>('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: 'DELETE' }),

  // User Preferences & Usage
  getPreferences: () => request<UserPreferences>('/api/user/preferences'),
  updatePreferences: (payload: Partial<UserPreferences>) =>
    request<UserPreferences>('/api/user/preferences', { method: 'PATCH', body: JSON.stringify(payload) }),
  updateProfile: (username: string) =>
    request<UserSummary>('/api/user/profile', { method: 'PATCH', body: JSON.stringify({ username }) }),
  getUsage: () => request<UsageStats>('/api/user/usage'),

  // Admin
  getAdminOverview: () => request<AdminOverview>('/api/admin/overview'),
  updateUserPlan: (userId: string, subscription_plan: 'free' | 'pro' | 'enterprise') =>
    request<{ id: string; subscription_plan: string }>(`/api/admin/users/${userId}/plan`, {
      method: 'PATCH',
      body: JSON.stringify({ subscription_plan }),
    }),
};

