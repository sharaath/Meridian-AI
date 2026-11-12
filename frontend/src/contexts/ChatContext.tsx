import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { AIModelInfo, Conversation, ProjectItem } from '@/types/api';

interface ChatContextValue {
  conversations: Conversation[];
  projects: ProjectItem[];
  models: AIModelInfo[];
  defaultModel: string | null;
  selectedProjectId: string | null;
  searchQuery: string;
  setSelectedProjectId: (id: string | null) => void;
  setSearchQuery: (q: string) => void;
  refreshSidebar: () => Promise<void>;
  refreshModels: () => Promise<void>;
}

const ChatContext = createContext<ChatContextValue>({
  conversations: [],
  projects: [],
  models: [],
  defaultModel: null,
  selectedProjectId: null,
  searchQuery: '',
  setSelectedProjectId: () => {},
  setSearchQuery: () => {},
  refreshSidebar: async () => {},
  refreshModels: async () => {},
});

export function ChatProvider({ children }: { children: React.ReactNode }) {
  const { token } = useAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [models, setModels] = useState<AIModelInfo[]>([]);
  const [defaultModel, setDefaultModel] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  const refreshModels = useCallback(async () => {
    try {
      const res = await api.listModels();
      setModels(res.models);
      setDefaultModel(res.default_model);
    } catch {
      setModels([]);
      setDefaultModel(null);
    }
  }, []);

  const refreshSidebar = useCallback(async () => {
    if (!token) return;
    try {
      const [convs, projs] = await Promise.all([
        api.listConversations(searchQuery || undefined, selectedProjectId || undefined),
        api.listProjects(),
      ]);
      setConversations(convs);
      setProjects(projs);
    } catch {
      // Ignore transient errors during refresh
    }
  }, [token, searchQuery, selectedProjectId]);

  useEffect(() => {
    refreshModels();
  }, [refreshModels]);

  useEffect(() => {
    refreshSidebar();
  }, [refreshSidebar]);

  return (
    <ChatContext.Provider
      value={{
        conversations,
        projects,
        models,
        defaultModel,
        selectedProjectId,
        searchQuery,
        setSelectedProjectId,
        setSearchQuery,
        refreshSidebar,
        refreshModels,
      }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}

