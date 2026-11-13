export type AssistantMode =
  | 'general'
  | 'coding'
  | 'writing'
  | 'email'
  | 'translation'
  | 'tutor'
  | 'math';

export interface UserSummary {
  id: string;
  email: string;
  username: string;
  role: 'user' | 'admin';
  subscription_plan: 'free' | 'pro' | 'enterprise';
  email_verified: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  auth_provider: string;
  user: UserSummary;
  verification_notice?: string | null;
}

export interface AIModelInfo {
  id: string;
  name: string;
  provider: string;
  description: string;
  context_window: number;
  max_output_tokens: number;
  supports_vision: boolean;
  supports_streaming: boolean;
  supports_audio: boolean;
  required_env_var: string;
  configured: boolean;
}

export interface ProviderStatus {
  provider: string;
  configured: boolean;
  required_env_var: string;
  models: string[];
}

export interface Citation {
  title: string;
  url: string;
  snippet: string;
  source: string;
}

export interface MessageAttachmentMeta {
  file_id: string;
  filename: string;
  file_type: string;
  mime_type: string;
  page_count?: number;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model_id: string;
  citations_json: Citation[];
  attachments_json: MessageAttachmentMeta[];
  token_count: number;
  is_edited: boolean;
  created_at: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  project_id: string | null;
  title: string;
  model_id: string;
  mode: AssistantMode;
  is_pinned: boolean;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface UploadedFile {
  id: string;
  user_id: string;
  conversation_id: string | null;
  project_id: string | null;
  filename: string;
  file_type: 'document' | 'image' | 'audio';
  mime_type: string;
  file_size: number;
  processing_status: 'pending' | 'processing' | 'ready' | 'failed';
  page_count: number;
  error_message: string;
  created_at: string;
  extracted_text?: string;
  pages_json?: Array<{ page: number; text: string }>;
}

export interface MemoryItem {
  id: string;
  user_id: string;
  memory_content: string;
  category: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectItem {
  id: string;
  user_id: string;
  name: string;
  description: string;
  custom_instructions: string;
  color: string;
  created_at: string;
  updated_at: string;
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system';
  preferred_model: string;
  custom_instructions: string;
  memory_enabled: boolean;
  web_search_enabled: boolean;
  voice_auto_play: boolean;
  settings: Record<string, unknown>;
  updated_at: string;
}

export interface UsageStats {
  subscription_plan: string;
  daily_limits: {
    messages_used: number;
    messages_limit: number | null;
    tokens_used: number;
    tokens_limit: number | null;
  };
  thirty_day_summary: {
    requests: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  totals: {
    conversations: number;
    messages: number;
    files: number;
  };
  by_model: Array<{
    model_id: string;
    requests: number;
    total_tokens: number;
  }>;
}

export interface EditChecklistItem {
  id: number;
  instruction: string;
  status: 'done' | 'missed' | 'clarification_needed';
  summary: string;
}

export interface DiffChunk {
  type: 'added' | 'removed' | 'unchanged';
  text: string;
  line_number_old?: number | null;
  line_number_new?: number | null;
}

export interface DiffSummary {
  unified_diff: string;
  added_count: number;
  removed_count: number;
  chunks: DiffChunk[];
}

export interface AmbiguityCheck {
  is_ambiguous: boolean;
  clarifying_question?: string | null;
  options: string[];
}

export interface PreciseEditResponse {
  success: boolean;
  original_text: string;
  edited_text: string;
  checklist: EditChecklistItem[];
  diff: DiffSummary;
  ambiguity?: AmbiguityCheck | null;
  unrelated_notes: string[];
  syntax_valid?: boolean | null;
  syntax_error?: string | null;
  version_id?: string | null;
  version_number: number;
}

export interface VersionHistoryItem {
  version_id: string;
  version_number: number;
  timestamp: string;
  instruction: string;
  content: string;
  diff_summary?: DiffSummary | null;
  status: 'current' | 'accepted' | 'rejected' | 'superseded';
}

export interface VersionHistoryResponse {
  resource_id: string;
  current_version_id: string;
  versions: VersionHistoryItem[];
}

export interface AdminOverview {
  metrics: {
    total_users: number;
    total_conversations: number;
    total_messages: number;
    total_files: number;
    total_tokens: number;
    rate_limit_blocked: number;
  };
  providers: ProviderStatus[];
  users: UserSummary[];
}

