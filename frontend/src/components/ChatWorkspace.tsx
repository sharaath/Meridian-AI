import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  useWindowDimensions,
  View,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import * as Speech from 'expo-speech';
import { Audio } from 'expo-av';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { DocumentPreviewModal } from '@/components/DocumentPreviewModal';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useAuth } from '@/contexts/AuthContext';
import { useChat } from '@/contexts/ChatContext';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { AssistantMode, Citation, ConversationDetail, Message, ToolStatusEvent, UploadedFile } from '@/types/api';

const MODES: Array<{ id: AssistantMode; label: string; icon: keyof typeof Ionicons.glyphMap }> = [
  { id: 'general', label: 'General', icon: 'sparkles-outline' },
  { id: 'coding', label: 'Coding', icon: 'code-slash-outline' },
  { id: 'writing', label: 'Writing', icon: 'create-outline' },
  { id: 'email', label: 'Email', icon: 'mail-outline' },
  { id: 'translation', label: 'Translate', icon: 'language-outline' },
  { id: 'tutor', label: 'Tutor', icon: 'school-outline' },
  { id: 'math', label: 'Math', icon: 'calculator-outline' },
];

const STARTER_PROMPTS: Array<{ title: string; prompt: string; mode: AssistantMode }> = [
  {
    title: 'Debug & optimize code',
    prompt: 'Review a Python FastAPI endpoint for race conditions and show an optimized async version.',
    mode: 'coding',
  },
  {
    title: 'Analyze a document or PDF',
    prompt: 'Summarize the key findings, risks, and action items from the file I attach.',
    mode: 'general',
  },
  {
    title: 'Learn a concept step by step',
    prompt: 'Teach me how Transformer attention works with a clear intuition and a worked numerical example.',
    mode: 'tutor',
  },
  {
    title: 'Draft a crisp executive email',
    prompt: 'Draft a concise project status update email covering milestones, blockers, and next steps.',
    mode: 'email',
  },
];

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

export function ChatWorkspace({ conversationId }: { conversationId?: string }) {
  const { width } = useWindowDimensions();
  const isWideSplit = width >= 1080;
  const { palette } = useTheme();
  const { user } = useAuth();
  const { models, defaultModel, selectedProjectId, refreshSidebar } = useChat();
  const router = useRouter();

  const [conv, setConv] = useState<ConversationDetail | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loadingConv, setLoadingConv] = useState(false);

  const [input, setInput] = useState('');
  const [mode, setMode] = useState<AssistantMode>('general');
  const [selectedModel, setSelectedModel] = useState<string | null>(defaultModel);
  const [useWebSearch, setUseWebSearch] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<UploadedFile[]>([]);
  const [uploadingFile, setUploadingFile] = useState(false);

  const [streaming, setStreaming] = useState(false);
  const [streamDraft, setStreamDraft] = useState('');
  const [streamCitations, setStreamCitations] = useState<Citation[]>([]);
  const [followUps, setFollowUps] = useState<string[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [lastFailedPrompt, setLastFailedPrompt] = useState<string | null>(null);

  const [editingMsgId, setEditingMsgId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');
  const [copiedMsgId, setCopiedMsgId] = useState<string | null>(null);
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null);
  const [selectedBranches, setSelectedBranches] = useState<Record<string, string>>({});
  const [toolStatus, setToolStatus] = useState<ToolStatusEvent | null>(null);

  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const [shareModalOpen, setShareModalOpen] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [previewMsg, setPreviewMsg] = useState<Message | null>(null);

  // Voice recording state
  const [isRecording, setIsRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const recordingRef = useRef<Audio.Recording | null>(null);
  const speechRecRef = useRef<any>(null);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    if (!selectedModel && defaultModel) {
      setSelectedModel(defaultModel);
    }
  }, [defaultModel, selectedModel]);

  useEffect(() => {
    if (!conversationId) {
      setConv(null);
      setMessages([]);
      setFollowUps([]);
      setErrorMsg(null);
      return;
    }
    let mounted = true;
    setLoadingConv(true);
    api
      .getConversation(conversationId)
      .then((detail) => {
        if (!mounted) return;
        setConv(detail);
        setMessages(detail.messages);
        setMode(detail.mode);
        if (detail.model_id) setSelectedModel(detail.model_id);
      })
      .catch((err) => {
        if (mounted) setErrorMsg(err.message || 'Failed to load conversation.');
      })
      .finally(() => {
        if (mounted) setLoadingConv(false);
      });
    return () => {
      mounted = false;
    };
  }, [conversationId]);

  const scrollToBottom = () => {
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 60);
  };

  const handlePickDocument = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({
        type: [
          'application/pdf',
          'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          'text/plain',
          'text/markdown',
          'text/csv',
        ],
        copyToCacheDirectory: true,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      setUploadingFile(true);
      setErrorMsg(null);
      const uploaded = await api.uploadFile(
        {
          uri: asset.uri,
          name: asset.name,
          type: asset.mimeType || 'application/octet-stream',
          webFile: (asset as any).file,
        },
        conv?.id
      );
      setAttachedFiles((prev) => [...prev, uploaded]);
    } catch (err: any) {
      setErrorMsg(err.message || 'Document upload failed.');
    } finally {
      setUploadingFile(false);
    }
  };

  const handlePickImage = async () => {
    try {
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        quality: 0.85,
      });
      if (res.canceled || !res.assets?.[0]) return;
      const asset = res.assets[0];
      const name = asset.fileName || `image-${Date.now()}.jpg`;
      setUploadingFile(true);
      setErrorMsg(null);
      const uploaded = await api.uploadFile(
        {
          uri: asset.uri,
          name,
          type: asset.mimeType || 'image/jpeg',
          webFile: (asset as any).file,
        },
        conv?.id
      );
      setAttachedFiles((prev) => [...prev, uploaded]);
    } catch (err: any) {
      setErrorMsg(err.message || 'Image upload failed.');
    } finally {
      setUploadingFile(false);
    }
  };

  const toggleVoiceInput = async () => {
    // Web Speech API when available
    if (Platform.OS === 'web' && typeof window !== 'undefined') {
      const SpeechRecognition =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (SpeechRecognition) {
        if (isRecording && speechRecRef.current) {
          speechRecRef.current.stop();
          setIsRecording(false);
          return;
        }
        const rec = new SpeechRecognition();
        rec.lang = 'en-US';
        rec.interimResults = true;
        rec.continuous = true;
        rec.onresult = (event: any) => {
          let transcript = '';
          for (let i = 0; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
          }
          setInput(transcript.trim());
        };
        rec.onerror = () => setIsRecording(false);
        rec.onend = () => setIsRecording(false);
        speechRecRef.current = rec;
        rec.start();
        setIsRecording(true);
        return;
      }
    }

    // Native / Expo AV audio recording -> backend Gemini transcription
    if (isRecording && recordingRef.current) {
      try {
        setIsRecording(false);
        setTranscribing(true);
        await recordingRef.current.stopAndUnloadAsync();
        const uri = recordingRef.current.getURI();
        recordingRef.current = null;
        if (uri) {
          const res = await api.transcribeAudio(uri, 'audio/m4a');
          if (res.transcript) {
            setInput((prev) => (prev ? `${prev} ${res.transcript}` : res.transcript));
          }
        }
      } catch (err: any) {
        setErrorMsg(err.message || 'Voice transcription failed.');
      } finally {
        setTranscribing(false);
      }
      return;
    }

    try {
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        setErrorMsg('Microphone permission is required for voice input.');
        return;
      }
      await Audio.setAudioModeAsync({ allowsRecordingIOS: true, playsInSilentModeIOS: true });
      const { recording } = await Audio.Recording.createAsync(Audio.RecordingOptionsPresets.HIGH_QUALITY);
      recordingRef.current = recording;
      setIsRecording(true);
    } catch (err: any) {
      setErrorMsg(err.message || 'Could not start audio recording.');
    }
  };

  const toggleSpeak = (msg: Message) => {
    if (speakingMsgId === msg.id) {
      Speech.stop();
      if (Platform.OS === 'web' && typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      setSpeakingMsgId(null);
      return;
    }

    setSpeakingMsgId(msg.id);
    if (Platform.OS === 'web' && typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(msg.content);
      utter.onend = () => setSpeakingMsgId(null);
      utter.onerror = () => setSpeakingMsgId(null);
      window.speechSynthesis.speak(utter);
    } else {
      Speech.speak(msg.content, {
        onDone: () => setSpeakingMsgId(null),
        onStopped: () => setSpeakingMsgId(null),
        onError: () => setSpeakingMsgId(null),
      });
    }
  };

  const handleStopStreaming = async () => {
    const draft = streamDraft.trim();
    abortRef.current?.abort();
    abortRef.current = null;
    setStreaming(false);

    const activeConvId = conv?.id;
    if (activeConvId) {
      api.cancelStream(activeConvId).catch(() => { });
    }

    if (draft) {
      const partialAssistant: Message = {
        id: `partial-${Date.now()}`,
        conversation_id: activeConvId || '',
        role: 'assistant',
        content: draft,
        model_id: selectedModel || '',
        citations_json: streamCitations,
        attachments_json: [],
        token_count: 0,
        is_edited: false,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, partialAssistant]);
      setStreamDraft('');
    }
  };

  const handleToggleFeedback = async (messageId: string, type: 'thumbs_up' | 'thumbs_down') => {
    const target = messages.find((m) => m.id === messageId);
    if (!target) return;
    const nextFeedback = target.feedback === type ? null : type;

    // Optimistic UI update
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, feedback: nextFeedback } : m))
    );

    try {
      await api.setMessageFeedback(messageId, nextFeedback);
    } catch {
      // Revert if error
      setMessages((prev) =>
        prev.map((m) => (m.id === messageId ? { ...m, feedback: target.feedback } : m))
      );
    }
  };

  const handleSend = async (overridePrompt?: string) => {
    const prompt = (overridePrompt ?? input).trim();
    if (!prompt || streaming) return;

    setErrorMsg(null);
    setLastFailedPrompt(null);
    setFollowUps([]);
    if (!overridePrompt) setInput('');

    // Determine parent message (last message on the current active branch)
    const { visible: currentVisible } = getVisibleMessages();
    const parentMsg = currentVisible.length > 0 ? currentVisible[currentVisible.length - 1] : null;

    const optimisticUser: Message = {
      id: `temp-user-${Date.now()}`,
      conversation_id: conv?.id || '',
      role: 'user',
      content: prompt,
      model_id: selectedModel || '',
      citations_json: [],
      attachments_json: attachedFiles.map((f) => ({
        file_id: f.id,
        filename: f.filename,
        file_type: f.file_type,
        mime_type: f.mime_type,
        page_count: f.page_count,
      })),
      token_count: 0,
      is_edited: false,
      parent_id: parentMsg ? parentMsg.id : null,
      created_at: new Date().toISOString(),
    };

    const filesToSend = attachedFiles.map((f) => f.id);
    setAttachedFiles([]);
    setMessages((prev) => [...prev, optimisticUser]);
    setStreaming(true);
    setStreamDraft('');
    setStreamCitations([]);
    scrollToBottom();

    const controller = new AbortController();
    abortRef.current = controller;
    let createdConvId = conv?.id || null;

    try {
      await api.streamChat(
        {
          conversation_id: createdConvId,
          project_id: selectedProjectId,
          content: prompt,
          model_id: selectedModel,
          mode,
          attachment_ids: filesToSend,
          use_web_search: useWebSearch,
          parent_id: parentMsg ? parentMsg.id : null,
        },
        {
          onMeta: (meta) => {
            createdConvId = meta.conversation_id;
            setStreamCitations(meta.citations || []);
            if (meta.has_summary) {
              setConv((prev) => (prev ? { ...prev, has_summary: true, summary: meta.summary ?? prev.summary } : prev));
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === optimisticUser.id
                  ? { ...m, id: meta.user_message_id, conversation_id: meta.conversation_id }
                  : m
              )
            );
          },
          onDelta: (delta) => {
            setStreamDraft((prev) => prev + delta);
            scrollToBottom();
          },
          onToolStatus: (st) => {
            setToolStatus(st);
            if (st.status === 'completed') {
              setTimeout(() => setToolStatus(null), 1400);
            }
          },
          onDone: async (donePayload) => {
            setToolStatus(null);
            setStreamDraft('');
            setStreaming(false);
            setMessages((prev) => [...prev, donePayload.assistant_message]);
            if (donePayload.assistant_message.parent_id) {
              setSelectedBranches((prev) => ({
                ...prev,
                [donePayload.assistant_message.parent_id!]: donePayload.assistant_message.id,
              }));
            }
            setFollowUps(donePayload.follow_ups || []);
            await refreshSidebar();
            if (!conversationId && donePayload.conversation_id) {
              router.replace(`/chat/${donePayload.conversation_id}` as never);
            }
            scrollToBottom();
          },
          onError: (detail) => {
            setToolStatus(null);
            setErrorMsg(detail);
            setLastFailedPrompt(prompt);
            setStreaming(false);
            if (detail.includes('Conversation not found')) {
              router.replace('/(app)/chat' as never);
            }
          },
        },
        controller.signal
      );
    } catch (err: any) {
      if (err?.name !== 'AbortError') {
        const msg = err?.message || 'Failed to get AI response.';
        setErrorMsg(msg);
        setLastFailedPrompt(prompt);
        if (msg.includes('Conversation not found')) {
          router.replace('/(app)/chat' as never);
        }
      }
      setStreaming(false);
      setStreamDraft('');
    } finally {
      abortRef.current = null;
    }
  };

  const handleRegenerate = async (targetMsg?: Message) => {
    if (!conv?.id || streaming) return;
    setErrorMsg(null);
    setStreaming(true);
    setStreamDraft('');

    // If targetMsg is provided (assistant), its parent is the user message; otherwise find last user message
    const parentId = targetMsg?.parent_id || (messages.filter((m) => m.role === 'user').slice(-1)[0]?.id);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await api.regenerateResponse(
        conv.id,
        { model_id: selectedModel, use_web_search: useWebSearch, parent_id: parentId },
        {
          onMeta: (meta) => setStreamCitations(meta.citations || []),
          onToolStatus: (st) => {
            setToolStatus(st);
            if (st.status === 'completed') {
              setTimeout(() => setToolStatus(null), 1400);
            }
          },
          onDelta: (delta) => setStreamDraft((prev) => prev + delta),
          onDone: (done) => {
            setToolStatus(null);
            setStreamDraft('');
            setStreaming(false);
            setMessages((prev) => [...prev, done.assistant_message]);
            if (done.assistant_message.parent_id) {
              setSelectedBranches((prev) => ({
                ...prev,
                [done.assistant_message.parent_id!]: done.assistant_message.id,
              }));
            }
            setFollowUps(done.follow_ups || []);
          },
          onError: (detail) => {
            setToolStatus(null);
            setErrorMsg(detail);
            setStreaming(false);
          },
        },
        controller.signal
      );
    } catch (err: any) {
      setToolStatus(null);
      if (err?.name !== 'AbortError') setErrorMsg(err?.message || 'Regeneration failed.');
      setStreaming(false);
      setStreamDraft('');
    }
  };

  const handleSaveEdit = async (messageId: string) => {
    const nextText = editingText.trim();
    if (!nextText || streaming) return;
    const targetMsg = messages.find((m) => m.id === messageId);
    setEditingMsgId(null);
    setErrorMsg(null);

    setStreaming(true);
    setStreamDraft('');
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await api.editAndResend(
        messageId,
        {
          content: nextText,
          model_id: selectedModel,
          use_web_search: useWebSearch,
          parent_id: targetMsg?.parent_id || null,
        },
        {
          onMeta: (meta) => {
            setStreamCitations(meta.citations || []);
            // Update chosen branch for this parent
            if (targetMsg?.parent_id || meta.parent_id) {
              setSelectedBranches((prev) => ({
                ...prev,
                [targetMsg?.parent_id || 'root']: meta.user_message_id,
              }));
            }
          },
          onToolStatus: (st) => {
            setToolStatus(st);
            if (st.status === 'completed') {
              setTimeout(() => setToolStatus(null), 1400);
            }
          },
          onDelta: (delta) => setStreamDraft((prev) => prev + delta),
          onDone: (done) => {
            setToolStatus(null);
            setStreamDraft('');
            setStreaming(false);
            setMessages((prev) => [...prev, done.assistant_message]);
            if (done.assistant_message.parent_id) {
              setSelectedBranches((prev) => ({
                ...prev,
                [done.assistant_message.parent_id!]: done.assistant_message.id,
              }));
            }
            setFollowUps(done.follow_ups || []);
          },
          onError: (detail) => {
            setToolStatus(null);
            setErrorMsg(detail);
            setStreaming(false);
          },
        },
        controller.signal
      );
    } catch (err: any) {
      setToolStatus(null);
      if (err?.name !== 'AbortError') setErrorMsg(err?.message || 'Edit failed.');
      setStreaming(false);
      setStreamDraft('');
    }
  };

  // Message Tree Traversal: reconstruct visible path and branch indices (< 1/2 >)
  const getVisibleMessages = (): {
    visible: Message[];
    branchInfo: Record<string, { index: number; total: number; siblings: Message[] }>;
  } => {
    if (!messages.length) return { visible: [], branchInfo: {} };

    // Group messages by parent_id ('root' for null/empty)
    const childrenByParent = new Map<string, Message[]>();
    for (const msg of messages) {
      const pId = msg.parent_id || 'root';
      const list = childrenByParent.get(pId) || [];
      list.push(msg);
      childrenByParent.set(pId, list);
    }

    // Sort siblings chronologically
    for (const [_, list] of childrenByParent.entries()) {
      list.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
    }

    const visible: Message[] = [];
    const branchInfo: Record<string, { index: number; total: number; siblings: Message[] }> = {};

    let currentParent = 'root';
    const visited = new Set<string>();

    while (childrenByParent.has(currentParent)) {
      const siblings = childrenByParent.get(currentParent)!;
      if (!siblings.length) break;

      // Select active sibling from selectedBranches or default to newest one
      const chosenId = selectedBranches[currentParent];
      const selectedMsg = siblings.find((s) => s.id === chosenId) || siblings[siblings.length - 1];

      if (visited.has(selectedMsg.id)) break;
      visited.add(selectedMsg.id);

      visible.push(selectedMsg);

      if (siblings.length > 1) {
        const sIndex = siblings.findIndex((s) => s.id === selectedMsg.id);
        branchInfo[selectedMsg.id] = {
          index: sIndex + 1,
          total: siblings.length,
          siblings,
        };
      }

      currentParent = selectedMsg.id;
    }

    // If tree is unlinked (legacy conversation), fallback to showing all messages chronologically
    if (visible.length === 0 && messages.length > 0) {
      return { visible: messages, branchInfo: {} };
    }

    return { visible, branchInfo };
  };

  const downloadExport = async (fetchBlob: () => Promise<Blob>, filename: string, fallbackUrl: string) => {
    try {
      if (Platform.OS === 'web') {
        const blob = await fetchBlob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
      } else {
        Alert.alert('Export Ready', `Open ${fallbackUrl} in browser to download.`);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Export failed.');
    }
  };

  const handleExport = (format: 'txt' | 'pdf') => {
    if (!conv?.id) return;
    downloadExport(
      () => api.downloadExportText(conv.id, format),
      `meridian-${conv.id.slice(0, 8)}.${format}`,
      api.exportConversationUrl(conv.id, format)
    );
  };

  const handleSaveMessageFile = (messageId: string, format: 'pdf' | 'docx' | 'pptx') =>
    downloadExport(
      () => api.downloadMessageExport(messageId, format),
      `meridian-${format === 'pptx' ? 'slides' : 'document'}-${messageId.slice(0, 8)}.${format}`,
      api.exportMessageUrl(messageId, format)
    );

  const handleShare = async () => {
    if (!conv?.id) return;
    try {
      const res = await api.shareConversation(conv.id);
      const origin = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.origin : 'meridian://';
      setShareUrl(`${origin}/share/${res.share_token}`);
      setShareModalOpen(true);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to create share link.');
    }
  };

  const activeModelObj = models.find((m) => m.id === selectedModel);
  const isWelcomeState = !loadingConv && messages.length === 0 && !streaming;

  const hasArtifactContent = (text: string) =>
    text.includes('```') || /\bslide\s+\d+/i.test(text) || /^#{1,2}\s+/m.test(text);

  const renderComposerCard = () => (
    <View style={styles.composerInner}>
      {attachedFiles.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 8 }}>
          <View style={{ flexDirection: 'row', gap: 8 }}>
            {attachedFiles.map((f) => (
              <View key={f.id} style={[styles.attachedChip, { backgroundColor: palette.surfaceElevated, borderColor: palette.border }]}>
                <Ionicons
                  name={f.file_type === 'image' ? 'image-outline' : 'document-text-outline'}
                  size={14}
                  color={palette.accent}
                />
                <Text numberOfLines={1} style={{ fontSize: 12, color: palette.text, maxWidth: 160 }}>
                  {f.filename}
                </Text>
                <TouchableOpacity onPress={() => setAttachedFiles((prev) => prev.filter((x) => x.id !== f.id))}>
                  <Ionicons name="close-circle" size={15} color={palette.textMuted} />
                </TouchableOpacity>
              </View>
            ))}
          </View>
        </ScrollView>
      ) : null}

      <View
        style={[
          styles.composerBox,
          {
            backgroundColor: palette.surface,
            borderColor: palette.borderStrong,
          },
        ]}
      >
        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="How can I help you today?"
          placeholderTextColor={palette.textMuted}
          multiline
          onKeyPress={(e: any) => {
            if (Platform.OS === 'web' && e.nativeEvent.key === 'Enter' && !e.nativeEvent.shiftKey) {
              e.preventDefault?.();
              handleSend();
            }
          }}
          style={[styles.composerInput, { color: palette.text }]}
        />
        <View style={styles.composerToolbar}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <TouchableOpacity
              onPress={handlePickDocument}
              disabled={uploadingFile}
              style={[styles.toolBtn, { borderColor: palette.border }]}
            >
              {uploadingFile ? (
                <ActivityIndicator size="small" color={palette.accent} />
              ) : (
                <Ionicons name="add" size={19} color={palette.textSecondary} />
              )}
            </TouchableOpacity>
            <TouchableOpacity onPress={handlePickImage} disabled={uploadingFile} style={[styles.toolBtn, { borderColor: palette.border }]}>
              <Ionicons name="image-outline" size={17} color={palette.textSecondary} />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={toggleVoiceInput}
              disabled={transcribing}
              style={[
                styles.toolBtn,
                {
                  borderColor: isRecording ? palette.danger : palette.border,
                  backgroundColor: isRecording ? palette.dangerSoft : 'transparent',
                },
              ]}
            >
              {transcribing ? (
                <ActivityIndicator size="small" color={palette.accent} />
              ) : (
                <Ionicons
                  name={isRecording ? 'mic' : 'mic-outline'}
                  size={17}
                  color={isRecording ? palette.danger : palette.textSecondary}
                />
              )}
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setUseWebSearch((v) => !v)}
              style={[
                styles.searchToggle,
                {
                  backgroundColor: useWebSearch ? palette.accentSoft : 'transparent',
                  borderColor: useWebSearch ? palette.accent : palette.border,
                },
              ]}
            >
              <Ionicons name="globe-outline" size={14} color={useWebSearch ? palette.accent : palette.textMuted} />
              <Text style={{ fontSize: 12, fontWeight: '600', color: useWebSearch ? palette.accent : palette.textMuted }}>
                Search
              </Text>
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TouchableOpacity
              onPress={() => setModelPickerOpen(true)}
              style={[styles.inlineModelBtn, { backgroundColor: palette.surfaceElevated, borderColor: palette.border }]}
            >
              <Text numberOfLines={1} style={{ fontSize: 12, fontWeight: '600', color: palette.textSecondary, maxWidth: 130 }}>
                {activeModelObj ? activeModelObj.name : models.length ? 'Select Model' : 'No Model'}
              </Text>
              <Ionicons name="chevron-down" size={13} color={palette.textMuted} />
            </TouchableOpacity>

            {streaming ? (
              <TouchableOpacity onPress={handleStopStreaming} style={[styles.sendBtn, { backgroundColor: palette.danger }]}>
                <Ionicons name="stop" size={16} color="#FFFFFF" />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity
                onPress={() => handleSend()}
                disabled={!input.trim()}
                style={[styles.sendBtn, { backgroundColor: input.trim() ? palette.accent : palette.borderStrong }]}
              >
                <Ionicons name="arrow-up" size={18} color="#FFFFFF" />
              </TouchableOpacity>
            )}
          </View>
        </View>
      </View>
    </View>
  );

  return (
    <View style={[styles.splitRoot, { backgroundColor: palette.bg }]}>
      <View style={[styles.root, { backgroundColor: palette.bg }]}>
        {/* Minimalist Header */}
        <View style={[styles.header, { borderBottomColor: palette.border, backgroundColor: palette.bg }]}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, alignItems: 'center', flexGrow: 1, justifyContent: 'center' }}>
            {MODES.map((m) => {
              const active = mode === m.id;
              return (
                <TouchableOpacity
                  key={m.id}
                  onPress={() => setMode(m.id)}
                  style={[
                    styles.modeChip,
                    {
                      backgroundColor: active ? palette.accentSoft : 'transparent',
                      borderColor: active ? palette.accent : palette.border,
                    },
                  ]}
                >
                  <Ionicons name={m.icon} size={13} color={active ? palette.accent : palette.textMuted} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: active ? palette.accent : palette.textSecondary }}>
                    {m.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>

          {conv?.id ? (
            <View style={{ flexDirection: 'row', gap: 6 }}>
              <TouchableOpacity onPress={() => handleExport('txt')} style={[styles.headerActionBtn, { borderColor: palette.border }]}>
                <Text style={{ fontSize: 11.5, fontWeight: '600', color: palette.textSecondary }}>TXT</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => handleExport('pdf')} style={[styles.headerActionBtn, { borderColor: palette.border }]}>
                <Text style={{ fontSize: 11.5, fontWeight: '600', color: palette.textSecondary }}>PDF</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={handleShare} style={[styles.headerActionBtn, { borderColor: palette.border }]}>
                <Ionicons name="share-outline" size={15} color={palette.textSecondary} />
              </TouchableOpacity>
            </View>
          ) : null}
        </View>

        {/* Unconfigured provider banner */}
        {models.length === 0 ? (
          <View style={[styles.noticeBanner, { backgroundColor: palette.surfaceElevated, borderBottomColor: palette.border }]}>
            <Ionicons name="warning-outline" size={16} color={palette.warning} />
            <Text style={{ flex: 1, fontSize: 13, color: palette.textSecondary }}>
              No AI provider API key is configured on the backend. Add `GEMINI_API_KEY` to `backend/.env`.
            </Text>
            <TouchableOpacity onPress={() => router.push('/models' as never)}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: palette.accent }}>Model Settings</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {/* Conversation Body */}
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
          contentContainerStyle={[styles.scrollContent, isWelcomeState && styles.scrollContentCentered]}
        >
          {loadingConv ? (
            <View style={styles.centerState}>
              <ActivityIndicator size="large" color={palette.accent} />
            </View>
          ) : isWelcomeState ? (
            <View style={styles.welcomeWrap}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 18 }}>
                <MeridianLogo size={38} showText={false} />
                <Text
                  style={[
                    styles.welcomeTitle,
                    {
                      color: palette.text,
                      fontFamily: Platform.OS === 'web' ? 'Georgia, serif' : undefined,
                    },
                  ]}
                >
                  {getGreeting()}, {user?.username || 'there'}
                </Text>
              </View>

              {/* Centered Claude-style Composer */}
              {renderComposerCard()}

              <View style={styles.starterRow}>
                {STARTER_PROMPTS.map((item, idx) => (
                  <TouchableOpacity
                    key={idx}
                    onPress={() => {
                      setMode(item.mode);
                      handleSend(item.prompt);
                    }}
                    style={[styles.starterPill, { backgroundColor: palette.surface, borderColor: palette.border }]}
                  >
                    <Text style={{ fontSize: 12.5, fontWeight: '600', color: palette.textSecondary }}>
                      {item.title}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          ) : (
            <View style={styles.messagesColumn}>
              {/* Subtle Earlier Messages Summarized Indicator */}
              {conv?.has_summary ? (
                <View
                  style={[
                    styles.summaryBanner,
                    { backgroundColor: palette.surfaceElevated, borderColor: palette.border },
                  ]}
                >
                  <Ionicons name="sparkles" size={13} color={palette.accent} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: palette.textSecondary }}>
                    Earlier messages summarized
                  </Text>
                </View>
              ) : null}

              {(() => {
                const { visible: displayMessages, branchInfo } = getVisibleMessages();
                return displayMessages.map((msg, idx) => {
                  const isUser = msg.role === 'user';
                  const isLastAssistant = !isUser && idx === displayMessages.length - 1;
                  const bInfo = branchInfo[msg.id];

                  if (isUser) {
                    return (
                      <View key={msg.id} style={[styles.msgRow, styles.msgRowUser]}>
                        <View
                          style={[
                            styles.userBubble,
                            { backgroundColor: palette.surfaceElevated, borderColor: palette.border },
                          ]}
                        >
                          {/* Sibling Branch Switcher for User Message (< 1/2 >) */}
                          {bInfo ? (
                            <View style={[styles.branchSwitcher, { borderColor: palette.border, alignSelf: 'flex-start', marginBottom: 6 }]}>
                              <TouchableOpacity
                                disabled={bInfo.index <= 1}
                                onPress={() => {
                                  const prevSibling = bInfo.siblings[bInfo.index - 2];
                                  if (prevSibling) {
                                    setSelectedBranches((prev) => ({ ...prev, [msg.parent_id || 'root']: prevSibling.id }));
                                  }
                                }}
                                style={{ paddingHorizontal: 3, opacity: bInfo.index <= 1 ? 0.3 : 1 }}
                              >
                                <Ionicons name="chevron-back" size={12} color={palette.textSecondary} />
                              </TouchableOpacity>
                              <Text style={{ fontSize: 11, fontWeight: '700', color: palette.textSecondary }}>
                                {bInfo.index}/{bInfo.total}
                              </Text>
                              <TouchableOpacity
                                disabled={bInfo.index >= bInfo.total}
                                onPress={() => {
                                  const nextSibling = bInfo.siblings[bInfo.index];
                                  if (nextSibling) {
                                    setSelectedBranches((prev) => ({ ...prev, [msg.parent_id || 'root']: nextSibling.id }));
                                  }
                                }}
                                style={{ paddingHorizontal: 3, opacity: bInfo.index >= bInfo.total ? 0.3 : 1 }}
                              >
                                <Ionicons name="chevron-forward" size={12} color={palette.textSecondary} />
                              </TouchableOpacity>
                            </View>
                          ) : null}

                          {msg.attachments_json?.length ? (
                            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                              {msg.attachments_json.map((att, aIdx) => (
                                <View key={aIdx} style={[styles.attBadge, { backgroundColor: palette.surface }]}>
                                  <Ionicons name="attach" size={12} color={palette.accent} />
                                  <Text style={{ fontSize: 11.5, color: palette.textSecondary }}>{att.filename}</Text>
                                </View>
                              ))}
                            </View>
                          ) : null}

                          {editingMsgId === msg.id ? (
                            <View style={{ gap: 8 }}>
                              <TextInput
                                value={editingText}
                                onChangeText={setEditingText}
                                multiline
                                style={[styles.editInput, { color: palette.text, borderColor: palette.accent }]}
                              />
                              <View style={{ flexDirection: 'row', justifyContent: 'flex-end', gap: 10 }}>
                                <TouchableOpacity onPress={() => setEditingMsgId(null)}>
                                  <Text style={{ color: palette.textMuted, fontSize: 13, fontWeight: '600' }}>Cancel</Text>
                                </TouchableOpacity>
                                <TouchableOpacity onPress={() => handleSaveEdit(msg.id)}>
                                  <Text style={{ color: palette.accent, fontSize: 13, fontWeight: '700' }}>Save & Resend</Text>
                                </TouchableOpacity>
                              </View>
                            </View>
                          ) : (
                            <Text selectable style={{ fontSize: 15, lineHeight: 22, color: palette.text }}>
                              {msg.content}
                            </Text>
                          )}

                          <View style={[styles.msgActions, { justifyContent: 'flex-end', marginTop: 6 }]}>
                            <Text style={{ fontSize: 11, color: palette.textMuted }}>
                              {formatTime(msg.created_at)}
                              {msg.is_edited ? ' · edited' : ''}
                            </Text>
                            <TouchableOpacity
                              onPress={async () => {
                                await Clipboard.setStringAsync(msg.content);
                                setCopiedMsgId(msg.id);
                                setTimeout(() => setCopiedMsgId(null), 1600);
                              }}
                              style={styles.actionPill}
                            >
                              <Ionicons
                                name={copiedMsgId === msg.id ? 'checkmark' : 'copy-outline'}
                                size={13}
                                color={copiedMsgId === msg.id ? palette.success : palette.textMuted}
                              />
                              <Text style={{ fontSize: 11.5, color: palette.textMuted }}>
                                {copiedMsgId === msg.id ? 'Copied' : 'Copy'}
                              </Text>
                            </TouchableOpacity>
                            <TouchableOpacity
                              onPress={() => {
                                setEditingMsgId(msg.id);
                                setEditingText(msg.content);
                              }}
                              style={styles.actionPill}
                            >
                              <Ionicons name="pencil-outline" size={13} color={palette.textMuted} />
                              <Text style={{ fontSize: 11.5, color: palette.textMuted }}>Edit</Text>
                            </TouchableOpacity>
                          </View>
                        </View>
                      </View>
                    );
                  }

                  return (
                    <View key={msg.id} style={styles.assistantProseWrap}>
                      <View style={[styles.assistantHeader, { justifyContent: 'space-between' }]}>
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                          <MeridianLogo size={22} showText={false} />
                          <Text style={{ fontSize: 13, fontWeight: '700', color: palette.text }}>Meridian</Text>
                          <Text style={{ fontSize: 11.5, color: palette.textMuted }}>{formatTime(msg.created_at)}</Text>
                        </View>

                        {/* Sibling Branch Switcher for Assistant Message (< 1/2 >) */}
                        {bInfo ? (
                          <View style={[styles.branchSwitcher, { borderColor: palette.border, backgroundColor: palette.surfaceElevated }]}>
                            <TouchableOpacity
                              disabled={bInfo.index <= 1}
                              onPress={() => {
                                const prevSibling = bInfo.siblings[bInfo.index - 2];
                                if (prevSibling) {
                                  setSelectedBranches((prev) => ({ ...prev, [msg.parent_id || 'root']: prevSibling.id }));
                                }
                              }}
                              style={{ paddingHorizontal: 3, opacity: bInfo.index <= 1 ? 0.3 : 1 }}
                            >
                              <Ionicons name="chevron-back" size={12} color={palette.textSecondary} />
                            </TouchableOpacity>
                            <Text style={{ fontSize: 11, fontWeight: '700', color: palette.textSecondary }}>
                              {bInfo.index}/{bInfo.total}
                            </Text>
                            <TouchableOpacity
                              disabled={bInfo.index >= bInfo.total}
                              onPress={() => {
                                const nextSibling = bInfo.siblings[bInfo.index];
                                if (nextSibling) {
                                  setSelectedBranches((prev) => ({ ...prev, [msg.parent_id || 'root']: nextSibling.id }));
                                }
                              }}
                              style={{ paddingHorizontal: 3, opacity: bInfo.index >= bInfo.total ? 0.3 : 1 }}
                            >
                              <Ionicons name="chevron-forward" size={12} color={palette.textSecondary} />
                            </TouchableOpacity>
                          </View>
                        ) : null}
                      </View>

                      <MarkdownRenderer content={msg.content} />

                      {hasArtifactContent(msg.content) ? (
                        <TouchableOpacity
                          onPress={() => setPreviewMsg(msg)}
                          style={[styles.artifactCard, { backgroundColor: palette.surface, borderColor: palette.border }]}
                        >
                          <View style={[styles.artifactIcon, { backgroundColor: palette.accentSoft }]}>
                            <Ionicons name="layers-outline" size={18} color={palette.accent} />
                          </View>
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: 13.5, fontWeight: '700', color: palette.text }}>
                              Open Artifact & Document Viewer
                            </Text>
                            <Text style={{ fontSize: 12, color: palette.textMuted }}>
                              Preview formatted content, PDF, PowerPoint slides, or Word document
                            </Text>
                          </View>
                          <Ionicons name="chevron-forward" size={17} color={palette.textMuted} />
                        </TouchableOpacity>
                      ) : null}

                      {/* Citations */}
                      {msg.citations_json?.length ? (
                        <View style={[styles.citationsBox, { borderTopColor: palette.border }]}>
                          <Text style={{ fontSize: 11.5, fontWeight: '700', color: palette.textMuted, marginBottom: 4 }}>
                            Sources
                          </Text>
                          {msg.citations_json.map((cite, cIdx) => (
                            <TouchableOpacity
                              key={cIdx}
                              onPress={() => cite.url && Linking.openURL(cite.url).catch(() => { })}
                              style={{ marginBottom: 3 }}
                            >
                              <Text numberOfLines={1} style={{ fontSize: 12, color: palette.accent }}>
                                [{cIdx + 1}] {cite.title}
                              </Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      ) : null}

                      {/* Message Action Bar */}
                      <View style={styles.msgActions}>
                        {/* Copy Button */}
                        <TouchableOpacity
                          onPress={async () => {
                            await Clipboard.setStringAsync(msg.content);
                            setCopiedMsgId(msg.id);
                            setTimeout(() => setCopiedMsgId(null), 1600);
                          }}
                          style={styles.actionPill}
                        >
                          <Ionicons
                            name={copiedMsgId === msg.id ? 'checkmark' : 'copy-outline'}
                            size={13}
                            color={copiedMsgId === msg.id ? palette.success : palette.textMuted}
                          />
                          <Text style={{ fontSize: 11.5, color: palette.textMuted }}>
                            {copiedMsgId === msg.id ? 'Copied' : 'Copy'}
                          </Text>
                        </TouchableOpacity>

                        {/* Thumbs Up Feedback */}
                        <TouchableOpacity
                          onPress={() => handleToggleFeedback(msg.id, 'thumbs_up')}
                          style={styles.actionPill}
                          accessibilityLabel="Helpful"
                        >
                          <Ionicons
                            name={msg.feedback === 'thumbs_up' ? 'thumbs-up' : 'thumbs-up-outline'}
                            size={13}
                            color={msg.feedback === 'thumbs_up' ? palette.accent : palette.textMuted}
                          />
                        </TouchableOpacity>

                        {/* Thumbs Down Feedback */}
                        <TouchableOpacity
                          onPress={() => handleToggleFeedback(msg.id, 'thumbs_down')}
                          style={styles.actionPill}
                          accessibilityLabel="Not helpful"
                        >
                          <Ionicons
                            name={msg.feedback === 'thumbs_down' ? 'thumbs-down' : 'thumbs-down-outline'}
                            size={13}
                            color={msg.feedback === 'thumbs_down' ? palette.danger : palette.textMuted}
                          />
                        </TouchableOpacity>

                        {/* Speak Button */}
                        <TouchableOpacity onPress={() => toggleSpeak(msg)} style={styles.actionPill}>
                          <Ionicons
                            name={speakingMsgId === msg.id ? 'stop-circle-outline' : 'volume-high-outline'}
                            size={14}
                            color={palette.textMuted}
                          />
                          <Text style={{ fontSize: 11.5, color: palette.textMuted }}>
                            {speakingMsgId === msg.id ? 'Stop' : 'Speak'}
                          </Text>
                        </TouchableOpacity>

                        {/* Regenerate Button */}
                        {!streaming ? (
                          <TouchableOpacity onPress={() => handleRegenerate(msg)} style={styles.actionPill}>
                            <Ionicons name="refresh-outline" size={13} color={palette.textMuted} />
                            <Text style={{ fontSize: 11.5, color: palette.textMuted }}>Regenerate</Text>
                          </TouchableOpacity>
                        ) : null}

                        <TouchableOpacity onPress={() => setPreviewMsg(msg)} style={styles.actionPill}>
                          <Ionicons name="eye-outline" size={14} color={palette.accent} />
                          <Text style={{ fontSize: 11.5, fontWeight: '700', color: palette.accent }}>Preview</Text>
                        </TouchableOpacity>

                        <TouchableOpacity onPress={() => handleSaveMessageFile(msg.id, 'pdf')} style={styles.actionPill}>
                          <Ionicons name="download-outline" size={14} color={palette.accent} />
                          <Text style={{ fontSize: 11.5, fontWeight: '600', color: palette.accent }}>PDF</Text>
                        </TouchableOpacity>

                        <TouchableOpacity onPress={() => handleSaveMessageFile(msg.id, 'docx')} style={styles.actionPill}>
                          <Ionicons name="document-text-outline" size={14} color={palette.accent} />
                          <Text style={{ fontSize: 11.5, fontWeight: '600', color: palette.accent }}>DOCX</Text>
                        </TouchableOpacity>

                        <TouchableOpacity onPress={() => handleSaveMessageFile(msg.id, 'pptx')} style={styles.actionPill}>
                          <Ionicons name="easel-outline" size={14} color={palette.accent} />
                          <Text style={{ fontSize: 11.5, fontWeight: '600', color: palette.accent }}>PPTX</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  );
                });
              })()}

              {/* Active Streaming Editorial Prose */}
              {streaming ? (
                <View style={styles.assistantProseWrap}>
                  <View style={styles.assistantHeader}>
                    <MeridianLogo size={22} showText={false} />
                    <Text style={{ fontSize: 13, fontWeight: '700', color: palette.text }}>Meridian</Text>
                    <ActivityIndicator size="small" color={palette.accent} />
                  </View>
                  {toolStatus ? (
                    <View style={[styles.toolStatusBadge, { backgroundColor: palette.surface, borderColor: palette.accent }]}>
                      <Ionicons
                        name={
                          toolStatus.tool === 'web_search'
                            ? 'globe-outline'
                            : toolStatus.tool === 'read_document'
                              ? 'document-text-outline'
                              : toolStatus.tool === 'generate_image'
                                ? 'image-outline'
                                : 'terminal-outline'
                        }
                        size={14}
                        color={palette.accent}
                      />
                      <Text style={{ fontSize: 12.5, fontWeight: '600', color: palette.accent }}>
                        {toolStatus.message}
                      </Text>
                      {toolStatus.status === 'running' ? (
                        <ActivityIndicator size="small" color={palette.accent} />
                      ) : (
                        <Ionicons name="checkmark-circle" size={14} color={palette.accent} />
                      )}
                    </View>
                  ) : null}
                  {streamDraft ? (
                    <MarkdownRenderer content={streamDraft} isStreaming={true} />
                  ) : (
                    <Text style={{ fontSize: 14, color: palette.textMuted }}>Thinking...</Text>
                  )}
                  {streamCitations.length > 0 ? (
                    <View style={[styles.citationsBox, { borderTopColor: palette.border }]}>
                      <Text style={{ fontSize: 11.5, color: palette.textMuted }}>
                        Retrieved {streamCitations.length} live web sources
                      </Text>
                    </View>
                  ) : null}
                </View>
              ) : null}

              {/* Follow-up Suggestions */}
              {!streaming && followUps.length > 0 ? (
                <View style={styles.followUpsWrap}>
                  {followUps.map((q, i) => (
                    <TouchableOpacity
                      key={i}
                      onPress={() => handleSend(q)}
                      style={[styles.followUpChip, { backgroundColor: palette.surface, borderColor: palette.border }]}
                    >
                      <Ionicons name="return-down-forward-outline" size={13} color={palette.accent} />
                      <Text style={{ fontSize: 12.5, color: palette.textSecondary }}>{q}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              ) : null}
            </View>
          )}
        </ScrollView>

        {/* Error & Retry Bar */}
        {errorMsg ? (
          <View style={[styles.errorBanner, { backgroundColor: palette.dangerSoft, borderColor: palette.danger }]}>
            <Ionicons name="alert-circle-outline" size={16} color={palette.danger} />
            <Text style={{ flex: 1, fontSize: 13, color: palette.danger }}>{errorMsg}</Text>
            {lastFailedPrompt ? (
              <TouchableOpacity onPress={() => handleSend(lastFailedPrompt)}>
                <Text style={{ fontSize: 13, fontWeight: '700', color: palette.danger }}>Retry</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}

        {/* Bottom Composer (when conversation is active) */}
        {!isWelcomeState ? (
          <View style={[styles.composerOuter, { backgroundColor: palette.bg }]}>
            {renderComposerCard()}
          </View>
        ) : null}
      </View>

      {/* Side-by-side Split Artifact Pane on wide desktop */}
      {isWideSplit && previewMsg ? (
        <DocumentPreviewModal
          visible
          inlinePane
          message={previewMsg}
          onClose={() => setPreviewMsg(null)}
          onDownload={(id, fmt) => handleSaveMessageFile(id, fmt)}
        />
      ) : null}

      {/* Model Selector Modal */}
      <Modal visible={modelPickerOpen} transparent animationType="fade" onRequestClose={() => setModelPickerOpen(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={{ fontSize: 17, fontWeight: '700', color: palette.text, marginBottom: 10 }}>
              Select AI Model
            </Text>
            {models.length === 0 ? (
              <Text style={{ fontSize: 13.5, color: palette.textSecondary, marginBottom: 14 }}>
                No models are currently configured. Add `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`) in
                `backend/.env` and restart the server.
              </Text>
            ) : (
              models.map((m) => {
                const active = m.id === selectedModel;
                return (
                  <TouchableOpacity
                    key={m.id}
                    onPress={() => {
                      setSelectedModel(m.id);
                      setModelPickerOpen(false);
                    }}
                    style={[
                      styles.modelOption,
                      {
                        borderColor: active ? palette.accent : palette.border,
                        backgroundColor: active ? palette.accentSoft : palette.bg,
                      },
                    ]}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 14.5, fontWeight: '700', color: palette.text }}>{m.name}</Text>
                      <Text style={{ fontSize: 12, color: palette.textMuted }}>{m.description}</Text>
                    </View>
                    {active ? <Ionicons name="checkmark-circle" size={18} color={palette.accent} /> : null}
                  </TouchableOpacity>
                );
              })
            )}
            <TouchableOpacity
              onPress={() => setModelPickerOpen(false)}
              style={[styles.closeModalBtn, { borderColor: palette.border }]}
            >
              <Text style={{ fontWeight: '600', color: palette.textSecondary }}>Close</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Share Link Modal */}
      <Modal visible={shareModalOpen} transparent animationType="fade" onRequestClose={() => setShareModalOpen(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={{ fontSize: 17, fontWeight: '700', color: palette.text, marginBottom: 8 }}>
              Share Conversation
            </Text>
            <Text style={{ fontSize: 13, color: palette.textSecondary, marginBottom: 10 }}>
              Anyone with this explicit link can view a read-only snapshot of this chat until you revoke it.
            </Text>
            <Text selectable style={[styles.shareLinkBox, { backgroundColor: palette.bg, borderColor: palette.border, color: palette.accent }]}>
              {shareUrl}
            </Text>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginTop: 12 }}>
              <TouchableOpacity
                onPress={async () => {
                  if (conv?.id) await api.revokeShare(conv.id);
                  setShareModalOpen(false);
                  setShareUrl(null);
                }}
              >
                <Text style={{ color: palette.danger, fontWeight: '600', fontSize: 13.5 }}>Revoke Link</Text>
              </TouchableOpacity>
              <View style={{ flexDirection: 'row', gap: 12 }}>
                <TouchableOpacity
                  onPress={async () => {
                    if (shareUrl) await Clipboard.setStringAsync(shareUrl);
                    setShareModalOpen(false);
                  }}
                >
                  <Text style={{ color: palette.accent, fontWeight: '700', fontSize: 13.5 }}>Copy Link</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setShareModalOpen(false)}>
                  <Text style={{ color: palette.textSecondary, fontWeight: '600', fontSize: 13.5 }}>Done</Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </View>
      </Modal>

      <DocumentPreviewModal
        visible={!isWideSplit && previewMsg !== null}
        message={previewMsg}
        onClose={() => setPreviewMsg(null)}
        onDownload={(id, fmt) => handleSaveMessageFile(id, fmt)}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  splitRoot: { flex: 1, flexDirection: 'row' },
  root: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  inlineModelBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    height: 34,
    borderRadius: 10,
    borderWidth: 1,
  },
  modeChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    borderWidth: 1,
  },
  headerActionBtn: {
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 8,
    borderWidth: 1,
  },
  noticeBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingVertical: 24,
    alignItems: 'center',
  },
  scrollContentCentered: {
    justifyContent: 'center',
  },
  centerState: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingVertical: 60 },
  welcomeWrap: {
    width: '100%',
    maxWidth: 760,
    alignItems: 'center',
  },
  welcomeTitle: { fontSize: 30, fontWeight: '600', letterSpacing: -0.4, textAlign: 'center' },
  starterRow: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 14,
    justifyContent: 'center',
  },
  starterPill: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
  },
  messagesColumn: { width: '100%', maxWidth: 760, gap: 22 },
  msgRow: { width: '100%', flexDirection: 'row' },
  msgRowUser: { justifyContent: 'flex-end' },
  userBubble: {
    maxWidth: '82%',
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  assistantProseWrap: {
    width: '100%',
    paddingVertical: 4,
    gap: 8,
  },
  assistantHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 2,
  },
  artifactCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderWidth: 1,
    borderRadius: 14,
    padding: 12,
    marginTop: 6,
  },
  artifactIcon: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  editInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 8,
    fontSize: 14.5,
    minHeight: 60,
  },
  branchSwitcher: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
    borderWidth: 1,
  },
  toolStatusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
    borderWidth: 1,
    alignSelf: 'flex-start',
    marginBottom: 10,
  },
  summaryBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    alignSelf: 'center',
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 20,
    borderWidth: 1,
    marginBottom: 12,
  },
  citationsBox: {
    marginTop: 10,
    paddingTop: 8,
    borderTopWidth: 1,
  },
  msgActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: 12,
    marginTop: 10,
  },
  actionPill: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  followUpsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  followUpChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
  },
  errorBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginHorizontal: 16,
    marginBottom: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
  },
  composerOuter: {
    paddingHorizontal: 20,
    paddingTop: 4,
    paddingBottom: 16,
    alignItems: 'center',
  },
  composerInner: { width: '100%', maxWidth: 760 },
  attachedChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 10,
    borderWidth: 1,
  },
  composerBox: {
    borderWidth: 1,
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingTop: 14,
    paddingBottom: 10,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  composerInput: {
    fontSize: 15,
    lineHeight: 22,
    maxHeight: 140,
    minHeight: 36,
    padding: 0,
  },
  composerToolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 8,
  },
  toolBtn: {
    width: 34,
    height: 34,
    borderRadius: 10,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  searchToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    height: 34,
    borderRadius: 10,
    borderWidth: 1,
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalCard: { width: '100%', maxWidth: 460, borderRadius: 16, borderWidth: 1, padding: 20 },
  modelOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    borderWidth: 1,
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
  },
  closeModalBtn: {
    marginTop: 8,
    alignItems: 'center',
    paddingVertical: 10,
    borderRadius: 10,
    borderWidth: 1,
  },
  shareLinkBox: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 10,
    fontSize: 13,
  },
});

