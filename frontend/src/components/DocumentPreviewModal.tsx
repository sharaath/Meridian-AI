import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { DiffChunk, EditChecklistItem, Message, PreciseEditResponse, VersionHistoryItem } from '@/types/api';

type PreviewTab = 'artifact' | 'edit' | 'pdf' | 'pptx' | 'docx';

interface SlideCardItem {
  icon?: string;
  label: string;
  text: string;
}

interface SlideItem {
  title: string;
  subtitle?: string;
  imageUrl?: string;
  imageAlt?: string;
  sectionHeader?: string;
  cards: SlideCardItem[];
  bullets: string[];
  footer?: string;
}

function stripInlineMd(text: string): string {
  return text.replace(/\*\*/g, '').replace(/__/g, '').replace(/`/g, '');
}

function parseSlidesFromMarkdown(content: string): SlideItem[] {
  const slides: SlideItem[] = [];
  let currentTitle = '';
  let currentSubtitle: string | undefined = undefined;
  let currentSectionHeader: string | undefined = undefined;
  let currentCards: SlideCardItem[] = [];
  let currentBullets: string[] = [];
  let currentImageUrl: string | undefined = undefined;
  let currentImageAlt: string | undefined = undefined;
  let currentFooter: string | undefined = undefined;

  const pushCurrent = () => {
    if (currentTitle || currentBullets.length || currentCards.length || currentImageUrl) {
      slides.push({
        title: currentTitle || `Slide ${slides.length + 1}`,
        subtitle: currentSubtitle,
        sectionHeader: currentSectionHeader,
        cards: currentCards,
        bullets: currentBullets,
        imageUrl: currentImageUrl,
        imageAlt: currentImageAlt,
        footer: currentFooter,
      });
      currentTitle = '';
      currentSubtitle = undefined;
      currentSectionHeader = undefined;
      currentCards = [];
      currentBullets = [];
      currentImageUrl = undefined;
      currentImageAlt = undefined;
      currentFooter = undefined;
    }
  };

  for (const raw of content.split('\n')) {
    const line = raw.trim();
    if (line === '---' || line === '***' || line === '___') {
      pushCurrent();
      continue;
    }

    const slideMatch = line.match(/^(?:\*\*)?Slide\s+\d+\s*[:\-–]\s*(.*?)(?:\*\*)?$/i);
    const heading1or2Match = line.match(/^#{1,2}\s+(.*)$/);
    if (slideMatch || heading1or2Match) {
      pushCurrent();
      currentTitle = stripInlineMd((slideMatch ? slideMatch[1] : heading1or2Match?.[1] || '').trim());
      continue;
    }

    // Section Header (### Heading)
    const h3Match = line.match(/^#{3}\s+(.*)$/);
    if (h3Match) {
      currentSectionHeader = stripInlineMd(h3Match[1].trim());
      continue;
    }

    // Detect markdown image tag: ![Caption](url)
    const imgMatch = line.match(/!\[(.*?)\]\((https?:\/\/[^\s)]+|\/[^\s)]+)\)/);
    if (imgMatch) {
      let src = imgMatch[2];
      if (src.startsWith('/')) {
        const base = process.env.EXPO_PUBLIC_API_URL || 'https://meridian-ai-vvvv.onrender.com';
        src = `${base}${src}`;
      }
      if (!currentImageUrl) {
        currentImageUrl = src;
        currentImageAlt = imgMatch[1];
      }
      const textWithoutImg = line.replace(/[-*•]?\s*!\[.*?\]\([^\s)]+\)/, '').trim();
      if (textWithoutImg) {
        currentBullets.push(stripInlineMd(textWithoutImg.replace(/^[-*]\s+/, '• ')));
      }
      continue;
    }

    // Subtitle detection: italic line right below title, before bullets/cards
    if (
      currentTitle &&
      !currentSubtitle &&
      !currentCards.length &&
      !currentBullets.length &&
      /^[*_]([^*_]+)[*_]$/.test(line)
    ) {
      const subMatch = line.match(/^[*_]([^*_]+)[*_]$/);
      if (subMatch) {
        currentSubtitle = subMatch[1].trim();
        continue;
      }
    }

    // Footer citation / source detection: e.g. *Source: ...* or *U.S. federal definition*
    if (/^\*(?:Source|Reference|Note)?:?\s*([^*]+)\*$/i.test(line)) {
      const footMatch = line.match(/^\*(?:Source|Reference|Note)?:?\s*([^*]+)\*$/i);
      if (footMatch) {
        currentFooter = footMatch[1].trim();
        continue;
      }
    }

    // Concept Card vs regular bullet detection
    if (line) {
      const cleaned = line.replace(/^[-*•]\s+/, '').trim();
      // Match card structure: optional emoji, label/keyword, colon/dash, description
      const cardMatch = cleaned.match(
        /^(?:([☀️⚡🌬️💨🌊♨️🌋♻️🔋💡🌱🌍🍃🪵💻⚙️🏭🏗️🔌🔬🏢🚗✈️🚢🛳️])\s*)?(?:\*\*)?([^:*–]+?)(?:\*\*)?\s*[:\-–]\s+(.*)$/
      );
      if (cardMatch && cardMatch[2].length <= 35 && cardMatch[3].length > 3) {
        currentCards.push({
          icon: cardMatch[1] || undefined,
          label: cardMatch[2].trim(),
          text: stripInlineMd(cardMatch[3].trim()),
        });
      } else {
        currentBullets.push(stripInlineMd(line.replace(/^[-*]\s+/, '• ')));
      }
    }
  }

  pushCurrent();
  return slides;
}

interface DocumentPreviewModalProps {
  visible: boolean;
  message: Message | null;
  onClose: () => void;
  onDownload: (messageId: string, format: 'pdf' | 'docx' | 'pptx') => void;
  inlinePane?: boolean;
}

export function DocumentPreviewModal({
  visible,
  message,
  onClose,
  onDownload,
  inlinePane = false,
}: DocumentPreviewModalProps) {
  const { palette } = useTheme();
  const [tab, setTab] = useState<PreviewTab>('artifact');
  const [slideIndex, setSlideIndex] = useState(0);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Phase 1B: Precise Editing & Diff State
  const [activeContent, setActiveContent] = useState<string>('');
  const [instructionText, setInstructionText] = useState<string>('');
  const [selectionText, setSelectionText] = useState<string>('');
  const [isApplyingEdit, setIsApplyingEdit] = useState<boolean>(false);
  const [editResponse, setEditResponse] = useState<PreciseEditResponse | null>(null);
  const [diffViewMode, setDiffViewMode] = useState<'diff' | 'preview'>('diff');
  const [versionHistory, setVersionHistory] = useState<VersionHistoryItem[]>([]);
  const [currentVersionIdx, setCurrentVersionIdx] = useState<number>(0);
  const [editError, setEditError] = useState<string | null>(null);

  useEffect(() => {
    if (message) {
      setActiveContent(message.content);
      setEditResponse(null);
      setInstructionText('');
      setSelectionText('');
      setEditError(null);
      setVersionHistory([
        {
          version_id: 'v1',
          version_number: 1,
          timestamp: new Date().toISOString(),
          instruction: 'Original Version',
          content: message.content,
          status: 'current',
        },
      ]);
      setCurrentVersionIdx(0);
    }
  }, [message]);

  const slides = useMemo(() => parseSlidesFromMarkdown(activeContent || message?.content || ''), [activeContent, message]);

  useEffect(() => {
    setSlideIndex(0);
    if (message && /\bslide\s+\d+/i.test(message.content)) {
      setTab('pptx');
    } else {
      setTab('artifact');
    }
  }, [message]);

  useEffect(() => {
    if (!visible || !message || tab !== 'pdf' || Platform.OS !== 'web') {
      return;
    }
    let active = true;
    let createdUrl: string | null = null;
    setLoadingPdf(true);
    setPdfError(null);

    api
      .downloadMessageExport(message.id, 'pdf')
      .then((blob) => {
        if (!active) return;
        createdUrl = URL.createObjectURL(blob);
        setPdfBlobUrl(createdUrl);
      })
      .catch((err: any) => {
        if (active) setPdfError(err?.message || 'Failed to render PDF preview.');
      })
      .finally(() => {
        if (active) setLoadingPdf(false);
      });

    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
      setPdfBlobUrl(null);
    };
  }, [visible, message, tab]);

  if (!visible || !message) return null;

  const activeSlide = slides[Math.min(slideIndex, Math.max(0, slides.length - 1))];
  const downloadFormat: 'pdf' | 'docx' | 'pptx' = tab === 'pptx' || tab === 'docx' ? tab : 'pdf';

  const handleApplyEdit = async () => {
    if (!instructionText.trim()) return;
    setIsApplyingEdit(true);
    setEditError(null);

    try {
      let res: PreciseEditResponse;
      if (selectionText.trim()) {
        res = await api.selectionEdit({
          full_content: activeContent,
          selection: selectionText.trim(),
          instruction: instructionText.trim(),
          resource_id: message.id,
        });
      } else {
        res = await api.preciseEdit({
          content: activeContent,
          instruction: instructionText.trim(),
          resource_id: message.id,
        });
      }

      setEditResponse(res);
      if (res.success) {
        const newVer: VersionHistoryItem = {
          version_id: res.version_id || `v${versionHistory.length + 1}`,
          version_number: versionHistory.length + 1,
          timestamp: new Date().toISOString(),
          instruction: instructionText.trim(),
          content: res.edited_text,
          diff_summary: res.diff,
          status: 'current',
        };
        const updated = [...versionHistory, newVer];
        setVersionHistory(updated);
        setCurrentVersionIdx(updated.length - 1);
        setActiveContent(res.edited_text);
        setDiffViewMode('diff');
      } else if (res.ambiguity?.is_ambiguous) {
        setEditError(res.ambiguity.clarifying_question || 'Instruction is ambiguous.');
      }
    } catch (err: any) {
      setEditError(err.message || 'Edit failed.');
    } finally {
      setIsApplyingEdit(false);
    }
  };

  const handleAccept = () => {
    if (!versionHistory.length) return;
    const current = versionHistory[currentVersionIdx];
    api.versionAction(message.id, current.version_id, 'accept').catch(() => {});
    setDiffViewMode('preview');
  };

  const handleReject = () => {
    if (versionHistory.length <= 1) return;
    const prevIdx = Math.max(0, currentVersionIdx - 1);
    const restored = versionHistory[prevIdx];
    setCurrentVersionIdx(prevIdx);
    setActiveContent(restored.content);
    setEditResponse(null);
    setDiffViewMode('preview');
  };

  const handleUndo = () => {
    if (currentVersionIdx > 0) {
      const prevIdx = currentVersionIdx - 1;
      const restored = versionHistory[prevIdx];
      setCurrentVersionIdx(prevIdx);
      setActiveContent(restored.content);
      if (restored.diff_summary) {
        setEditResponse({
          success: true,
          original_text: versionHistory[Math.max(0, prevIdx - 1)].content,
          edited_text: restored.content,
          checklist: [],
          diff: restored.diff_summary,
          unrelated_notes: [],
          version_number: restored.version_number,
        });
      }
    }
  };

  const renderPanelContent = () => (
    <View
      style={[
        inlinePane ? styles.inlineContainer : styles.dialog,
        { backgroundColor: palette.surface, borderColor: palette.border },
      ]}
    >
      {/* Header Tabs */}
      <View style={[styles.header, { borderBottomColor: palette.border }]}>
        <View style={styles.tabsRow}>
          {(
            [
              { id: 'artifact', label: 'Artifact', icon: 'sparkles-outline' },
              { id: 'edit', label: 'Precise Edit & Diff', icon: 'git-commit-outline' },
              { id: 'pdf', label: 'PDF', icon: 'document-outline' },
              { id: 'pptx', label: `Slides (${slides.length})`, icon: 'easel-outline' },
              { id: 'docx', label: 'Word', icon: 'document-text-outline' },
            ] as const
          ).map((item) => {
            const active = tab === item.id;
            return (
              <TouchableOpacity
                key={item.id}
                onPress={() => setTab(item.id)}
                style={[
                  styles.tabBtn,
                  {
                    backgroundColor: active ? palette.accentSoft : 'transparent',
                    borderColor: active ? palette.accent : palette.border,
                  },
                ]}
              >
                <Ionicons name={item.icon} size={13} color={active ? palette.accent : palette.textSecondary} />
                <Text style={{ fontSize: 12, fontWeight: '700', color: active ? palette.accent : palette.textSecondary }}>
                  {item.label}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <TouchableOpacity
            onPress={async () => {
              await Clipboard.setStringAsync(activeContent);
              setCopied(true);
              setTimeout(() => setCopied(false), 1600);
            }}
            style={[styles.closeBtn, { borderColor: palette.border, width: 'auto', paddingHorizontal: 8, gap: 4, flexDirection: 'row' }]}
          >
            <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={13} color={palette.textSecondary} />
            <Text style={{ fontSize: 12, color: palette.textSecondary, fontWeight: '600' }}>
              {copied ? 'Copied' : 'Copy'}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => onDownload(message.id, downloadFormat)}
            style={[styles.downloadBtn, { backgroundColor: palette.accent }]}
          >
            <Ionicons name="download-outline" size={14} color="#FFFFFF" />
            <Text style={{ color: '#FFFFFF', fontSize: 12, fontWeight: '700' }}>
              {downloadFormat.toUpperCase()}
            </Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onClose} style={[styles.closeBtn, { borderColor: palette.border }]}>
            <Ionicons name="close" size={17} color={palette.text} />
          </TouchableOpacity>
        </View>
      </View>

      {/* Body */}
      <View style={styles.body}>
        {/* Artifact View */}
        {tab === 'artifact' ? (
          <ScrollView contentContainerStyle={{ padding: 8 }}>
            <MarkdownRenderer content={activeContent} />
          </ScrollView>
        ) : null}

        {/* Phase 1B: Precise Edit & Diff View */}
        {tab === 'edit' ? (
          <View style={{ flex: 1, gap: 10 }}>
            {/* Edit Controls Toolbar */}
            <View style={[styles.editCard, { borderColor: palette.border, backgroundColor: palette.surfaceElevated }]}>
              <Text style={{ fontSize: 13, fontWeight: '700', color: palette.text }}>
                Phase 1B — Targeted Minimal-Change Editing
              </Text>

              {/* Selection Input (Optional) */}
              <TextInput
                value={selectionText}
                onChangeText={setSelectionText}
                placeholder="Specific selection to replace (optional — leave empty to edit whole document)..."
                placeholderTextColor={palette.textMuted}
                style={[styles.inputBox, { borderColor: palette.border, backgroundColor: palette.surface, color: palette.text, fontSize: 12 }]}
              />

              {/* Instruction Input */}
              <View style={{ flexDirection: 'row', gap: 6, alignItems: 'center' }}>
                <TextInput
                  value={instructionText}
                  onChangeText={setInstructionText}
                  placeholder="Exact edit instructions (e.g. 1. change title to X, 2. make para 2 shorter)..."
                  placeholderTextColor={palette.textMuted}
                  style={[styles.inputBox, { flex: 1, borderColor: palette.border, backgroundColor: palette.surface, color: palette.text }]}
                />
                <TouchableOpacity
                  disabled={isApplyingEdit || !instructionText.trim()}
                  onPress={handleApplyEdit}
                  style={[styles.applyBtn, { backgroundColor: palette.accent, opacity: isApplyingEdit || !instructionText.trim() ? 0.6 : 1 }]}
                >
                  {isApplyingEdit ? (
                    <ActivityIndicator size="small" color="#FFFFFF" />
                  ) : (
                    <>
                      <Ionicons name="flash-outline" size={14} color="#FFFFFF" />
                      <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 12 }}>Apply</Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>

              {/* Quick Pills */}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 4 }}>
                {[
                  'Shorten paragraph 2',
                  'Fix grammar & flow',
                  'Add executive summary section',
                  'Format into clean bullets',
                ].map((chip) => (
                  <TouchableOpacity
                    key={chip}
                    onPress={() => setInstructionText(chip)}
                    style={[styles.chipBtn, { borderColor: palette.border, backgroundColor: palette.surface }]}
                  >
                    <Text style={{ fontSize: 11, color: palette.textSecondary }}>{chip}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {/* Ambiguity or Error Alert */}
              {editError ? (
                <View style={[styles.alertBox, { backgroundColor: palette.accentSoft, borderColor: palette.accent }]}>
                  <Ionicons name="help-circle-outline" size={16} color={palette.accent} />
                  <Text style={{ fontSize: 12, color: palette.text, flex: 1 }}>{editError}</Text>
                </View>
              ) : null}
            </View>

            {/* Checklist Verification Breakdown */}
            {editResponse?.checklist?.length ? (
              <View style={[styles.checklistCard, { borderColor: palette.border, backgroundColor: palette.surfaceElevated }]}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: palette.text, marginBottom: 4 }}>
                  Checklist Verification ({editResponse.checklist.length} items applied)
                </Text>
                {editResponse.checklist.map((item) => (
                  <View key={item.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="checkmark-circle" size={14} color="#059669" />
                    <Text style={{ fontSize: 12, color: palette.textSecondary }}>
                      {item.summary || `Done: ${item.instruction}`}
                    </Text>
                  </View>
                ))}
                {editResponse.unrelated_notes?.map((note, i) => (
                  <Text key={i} style={{ fontSize: 11, fontStyle: 'italic', color: palette.textMuted }}>
                    Note (unchanged): {note}
                  </Text>
                ))}
              </View>
            ) : null}

            {/* Version Actions Bar: Accept / Reject / Undo */}
            <View style={[styles.versionBar, { borderColor: palette.border }]}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={{ fontSize: 12, fontWeight: '700', color: palette.text }}>
                  Version {currentVersionIdx + 1} of {versionHistory.length}
                </Text>
                {editResponse?.diff ? (
                  <Text style={{ fontSize: 11, color: palette.textMuted }}>
                    (+{editResponse.diff.added_count} / -{editResponse.diff.removed_count})
                  </Text>
                ) : null}
              </View>

              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                <TouchableOpacity
                  disabled={currentVersionIdx === 0}
                  onPress={handleUndo}
                  style={[styles.actionBtn, { borderColor: palette.border, opacity: currentVersionIdx === 0 ? 0.4 : 1 }]}
                >
                  <Ionicons name="arrow-undo-outline" size={13} color={palette.text} />
                  <Text style={{ fontSize: 11, fontWeight: '600', color: palette.text }}>Undo</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  disabled={versionHistory.length <= 1}
                  onPress={handleReject}
                  style={[styles.actionBtn, { borderColor: '#dc2626', opacity: versionHistory.length <= 1 ? 0.4 : 1 }]}
                >
                  <Ionicons name="close-circle-outline" size={13} color="#dc2626" />
                  <Text style={{ fontSize: 11, fontWeight: '600', color: '#dc2626' }}>Reject</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  onPress={handleAccept}
                  style={[styles.actionBtn, { backgroundColor: '#059669', borderColor: '#059669' }]}
                >
                  <Ionicons name="checkmark-circle-outline" size={13} color="#FFFFFF" />
                  <Text style={{ fontSize: 11, fontWeight: '700', color: '#FFFFFF' }}>Accept</Text>
                </TouchableOpacity>
              </View>
            </View>

            {/* Diff Viewer / Preview Switcher */}
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity
                onPress={() => setDiffViewMode('diff')}
                style={[styles.viewTab, diffViewMode === 'diff' && { borderColor: palette.accent }]}
              >
                <Text style={{ fontSize: 12, fontWeight: '600', color: diffViewMode === 'diff' ? palette.accent : palette.textMuted }}>
                  Diff View
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setDiffViewMode('preview')}
                style={[styles.viewTab, diffViewMode === 'preview' && { borderColor: palette.accent }]}
              >
                <Text style={{ fontSize: 12, fontWeight: '600', color: diffViewMode === 'preview' ? palette.accent : palette.textMuted }}>
                  Full Text View
                </Text>
              </TouchableOpacity>
            </View>

            {/* Diff Content Stage */}
            <ScrollView contentContainerStyle={{ paddingVertical: 6 }}>
              {diffViewMode === 'diff' && editResponse?.diff ? (
                <View style={[styles.diffWrap, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  {editResponse.diff.chunks.map((chunk, idx) => {
                    const isAdded = chunk.type === 'added';
                    const isRemoved = chunk.type === 'removed';
                    return (
                      <View
                        key={idx}
                        style={[
                          styles.diffLine,
                          isAdded && { backgroundColor: 'rgba(5, 150, 105, 0.12)' },
                          isRemoved && { backgroundColor: 'rgba(220, 38, 38, 0.12)' },
                        ]}
                      >
                        <Text style={{ width: 16, fontSize: 11, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', color: isAdded ? '#059669' : isRemoved ? '#dc2626' : palette.textMuted }}>
                          {isAdded ? '+' : isRemoved ? '-' : ' '}
                        </Text>
                        <Text
                          style={{
                            flex: 1,
                            fontSize: 12,
                            fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
                            color: isAdded ? '#059669' : isRemoved ? '#dc2626' : palette.text,
                            textDecorationLine: isRemoved ? 'line-through' : 'none',
                          }}
                        >
                          {chunk.text}
                        </Text>
                      </View>
                    );
                  })}
                </View>
              ) : (
                <MarkdownRenderer content={activeContent} />
              )}
            </ScrollView>
          </View>
        ) : null}

        {/* PDF View */}
        {tab === 'pdf' ? (
          Platform.OS === 'web' ? (
            loadingPdf ? (
              <View style={styles.centered}>
                <ActivityIndicator size="large" color={palette.accent} />
                <Text style={{ marginTop: 10, color: palette.textMuted }}>Rendering PDF preview...</Text>
              </View>
            ) : pdfError ? (
              <View style={styles.centered}>
                <Text style={{ color: palette.danger, fontSize: 14 }}>{pdfError}</Text>
              </View>
            ) : pdfBlobUrl ? (
              <View style={{ flex: 1, borderRadius: 10, overflow: 'hidden' }}>
                {React.createElement('iframe', {
                  src: pdfBlobUrl,
                  title: 'Meridian PDF Preview',
                  style: { width: '100%', height: '100%', border: 'none', backgroundColor: '#FFFFFF' },
                })}
              </View>
            ) : null
          ) : (
            <ScrollView contentContainerStyle={styles.paperWrap}>
              <View style={styles.paperPage}>
                <Text style={styles.paperBody}>{stripInlineMd(activeContent)}</Text>
              </View>
            </ScrollView>
          )
        ) : null}

        {/* PPTX View */}
        {tab === 'pptx' && activeSlide ? (
          <View style={styles.slideStage}>
            <View style={styles.slideCard}>
              <View style={styles.slideTopBar} />
              <ScrollView contentContainerStyle={styles.slideInnerScroll}>
                <View style={styles.slideContentLayout}>
                  {/* Left Column: Hero Graphic Illustration (if present) */}
                  {activeSlide.imageUrl ? (
                    <View style={styles.slideHeroCol}>
                      <Image
                        source={{ uri: activeSlide.imageUrl }}
                        style={styles.slideHeroImage}
                        resizeMode="cover"
                      />
                      {activeSlide.imageAlt ? (
                        <View style={styles.slideHeroOverlay}>
                          <Text numberOfLines={2} style={styles.slideHeroCaption}>
                            {activeSlide.imageAlt}
                          </Text>
                        </View>
                      ) : null}
                    </View>
                  ) : null}

                  {/* Right Column: Title, Subtitle, Section Header, Cards & Bullets */}
                  <View style={[styles.slideDeckCol, !activeSlide.imageUrl && { width: '100%', maxWidth: '100%' }]}>
                    <View style={styles.slideDeckHeader}>
                      <View style={styles.slideBadge}>
                        <Text style={styles.slideBadgeText}>SLIDE {slideIndex + 1} OF {slides.length}</Text>
                      </View>
                      <Text style={styles.slideTitle}>{activeSlide.title}</Text>
                      {activeSlide.subtitle ? (
                        <Text style={styles.slideSubtitle}>{activeSlide.subtitle}</Text>
                      ) : null}
                    </View>

                    {activeSlide.sectionHeader ? (
                      <Text style={styles.slideSectionHeader}>{activeSlide.sectionHeader}</Text>
                    ) : null}

                    {/* Structured Concept Cards */}
                    {activeSlide.cards.length > 0 ? (
                      <View style={styles.slideCardsContainer}>
                        {activeSlide.cards.map((card, cIdx) => (
                          <View key={cIdx} style={styles.slideConceptCard}>
                            <View style={styles.cardIconBadge}>
                              <Text style={styles.cardIconText}>{card.icon || '⚡'}</Text>
                            </View>
                            <View style={{ flex: 1 }}>
                              <Text style={styles.cardLabelText}>{card.label}</Text>
                              <Text style={styles.cardDescText}>{card.text}</Text>
                            </View>
                          </View>
                        ))}
                      </View>
                    ) : null}

                    {/* Standard Bullets if any */}
                    {activeSlide.bullets.length > 0 ? (
                      <View style={{ gap: 8, marginTop: 8 }}>
                        {activeSlide.bullets.map((b, i) => (
                          <Text key={i} style={styles.slideBullet}>
                            {b}
                          </Text>
                        ))}
                      </View>
                    ) : null}

                    {/* Footer / Citation */}
                    {activeSlide.footer ? (
                      <Text style={styles.slideFooterText}>{activeSlide.footer}</Text>
                    ) : null}
                  </View>
                </View>
              </ScrollView>
            </View>

            <View style={styles.slideControls}>
              <TouchableOpacity
                disabled={slideIndex === 0}
                onPress={() => setSlideIndex((i) => Math.max(0, i - 1))}
                style={[styles.navArrow, { borderColor: palette.border, opacity: slideIndex === 0 ? 0.4 : 1 }]}
              >
                <Ionicons name="chevron-back" size={16} color={palette.text} />
                <Text style={{ color: palette.text, fontWeight: '600', fontSize: 13 }}>Prev</Text>
              </TouchableOpacity>
              <Text style={{ color: palette.textSecondary, fontWeight: '700', fontSize: 13 }}>
                {slideIndex + 1} / {slides.length}
              </Text>
              <TouchableOpacity
                disabled={slideIndex >= slides.length - 1}
                onPress={() => setSlideIndex((i) => Math.min(slides.length - 1, i + 1))}
                style={[
                  styles.navArrow,
                  { borderColor: palette.border, opacity: slideIndex >= slides.length - 1 ? 0.4 : 1 },
                ]}
              >
                <Text style={{ color: palette.text, fontWeight: '600', fontSize: 13 }}>Next</Text>
                <Ionicons name="chevron-forward" size={16} color={palette.text} />
              </TouchableOpacity>
            </View>
          </View>
        ) : null}

        {/* Word Document View */}
        {tab === 'docx' ? (
          <ScrollView contentContainerStyle={styles.paperWrap}>
            <View style={styles.paperPage}>
              {activeContent.split('\n').map((raw, idx) => {
                const line = raw.trim();
                if (!line) return <View key={idx} style={{ height: 8 }} />;
                if (line.startsWith('# ')) {
                  return (
                    <Text key={idx} style={styles.docH1}>
                      {stripInlineMd(line.slice(2))}
                    </Text>
                  );
                }
                if (line.startsWith('## ')) {
                  return (
                    <Text key={idx} style={styles.docH2}>
                      {stripInlineMd(line.slice(3))}
                    </Text>
                  );
                }
                if (line.startsWith('### ')) {
                  return (
                    <Text key={idx} style={styles.docH3}>
                      {stripInlineMd(line.slice(4))}
                    </Text>
                  );
                }
                return (
                  <Text key={idx} style={styles.paperBody}>
                    {stripInlineMd(line.replace(/^[-*]\s+/, '•  '))}
                  </Text>
                );
              })}
            </View>
          </ScrollView>
        ) : null}
      </View>
    </View>
  );

  if (inlinePane) {
    return renderPanelContent();
  }

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>{renderPanelContent()}</View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  inlineContainer: {
    width: '48%',
    minWidth: 400,
    maxWidth: 720,
    height: '100%',
    borderLeftWidth: 1,
    overflow: 'hidden',
  },
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 16,
  },
  dialog: {
    width: '100%',
    maxWidth: 980,
    height: '88%',
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  tabsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  tabBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 8,
    borderWidth: 1,
  },
  downloadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },
  closeBtn: {
    width: 30,
    height: 30,
    borderRadius: 8,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, padding: 12 },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  slideStage: { flex: 1, justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  slideCard: {
    width: '100%',
    flex: 1,
    backgroundColor: '#FAF9F6',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    overflow: 'hidden',
  },
  slideTopBar: { height: 8, width: '100%', backgroundColor: '#0D9488' },
  slideInnerScroll: { padding: 20 },
  slideContentLayout: {
    flexDirection: Platform.OS === 'web' ? 'row' : 'column',
    gap: 20,
    alignItems: 'stretch',
  },
  slideHeroCol: {
    width: Platform.OS === 'web' ? 260 : '100%',
    minHeight: 280,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#0F172A',
    borderWidth: 1,
    borderColor: '#CBD5E1',
    position: 'relative',
  },
  slideHeroImage: {
    width: '100%',
    height: '100%',
    minHeight: 280,
  },
  slideHeroOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(15, 23, 42, 0.75)',
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  slideHeroCaption: {
    fontSize: 11,
    color: '#E2E8F0',
    fontStyle: 'italic',
    textAlign: 'center',
  },
  slideDeckCol: {
    flex: 1,
    gap: 10,
  },
  slideDeckHeader: {
    gap: 4,
  },
  slideBadge: {
    alignSelf: 'flex-start',
    backgroundColor: 'rgba(13, 148, 136, 0.12)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    marginBottom: 4,
  },
  slideBadgeText: {
    fontSize: 10.5,
    fontWeight: '800',
    color: '#0D9488',
    letterSpacing: 0.8,
  },
  slideTitle: { fontSize: 20, fontWeight: '800', color: '#0F172A', lineHeight: 26 },
  slideSubtitle: { fontSize: 13, fontStyle: 'italic', color: '#475569', lineHeight: 18 },
  slideSectionHeader: { fontSize: 14, fontWeight: '700', color: '#0F172A', marginTop: 4 },
  slideCardsContainer: { gap: 8, marginTop: 4 },
  slideConceptCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 8,
    padding: 9,
  },
  cardIconBadge: {
    width: 30,
    height: 30,
    borderRadius: 6,
    backgroundColor: '#F0FDF4',
    borderWidth: 1,
    borderColor: '#BBF7D0',
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardIconText: { fontSize: 16 },
  cardLabelText: { fontSize: 13, fontWeight: '700', color: '#0F172A' },
  cardDescText: { fontSize: 12, color: '#334155', lineHeight: 17, marginTop: 2 },
  slideFooterText: { fontSize: 11, color: '#64748B', fontStyle: 'italic', marginTop: 6 },
  slideBullet: { fontSize: 13.5, lineHeight: 20, color: '#1E293B' },
  slideControls: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  navArrow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
  },
  paperWrap: { alignItems: 'center', paddingVertical: 8 },
  paperPage: {
    width: '100%',
    maxWidth: 740,
    backgroundColor: '#FFFFFF',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    padding: 24,
    gap: 6,
  },
  docH1: { fontSize: 20, fontWeight: '800', color: '#0F172A', marginBottom: 4 },
  docH2: { fontSize: 16, fontWeight: '700', color: '#0D9488', marginTop: 8, marginBottom: 2 },
  docH3: { fontSize: 14, fontWeight: '700', color: '#0F172A', marginTop: 4 },
  paperBody: { fontSize: 13.5, lineHeight: 20, color: '#1E293B' },

  // Phase 1B Styling
  editCard: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    gap: 8,
  },
  inputBox: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 7,
    fontSize: 13,
  },
  applyBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 14,
    paddingVertical: 9,
    borderRadius: 8,
  },
  chipBtn: {
    borderWidth: 1,
    borderRadius: 14,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  alertBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: 8,
    borderRadius: 8,
    borderWidth: 1,
  },
  checklistCard: {
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    gap: 4,
  },
  versionBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 6,
    borderBottomWidth: 1,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: 6,
    borderWidth: 1,
  },
  viewTab: {
    paddingVertical: 4,
    paddingHorizontal: 10,
    borderBottomWidth: 2,
    borderColor: 'transparent',
  },
  diffWrap: {
    borderWidth: 1,
    borderRadius: 8,
    overflow: 'hidden',
  },
  diffLine: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
});
