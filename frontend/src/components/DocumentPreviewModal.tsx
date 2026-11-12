import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { Message } from '@/types/api';

type PreviewTab = 'artifact' | 'pdf' | 'pptx' | 'docx';

interface SlideItem {
  title: string;
  bullets: string[];
}

function stripInlineMd(text: string): string {
  return text.replace(/\*\*/g, '').replace(/__/g, '').replace(/`/g, '');
}

function parseSlidesFromMarkdown(content: string): SlideItem[] {
  const slides: SlideItem[] = [];
  let currentTitle = '';
  let currentBullets: string[] = [];

  for (const raw of content.split('\n')) {
    const line = raw.trim();
    if (line === '---' || line === '***' || line === '___') {
      if (currentTitle || currentBullets.length) {
        slides.push({ title: currentTitle || `Slide ${slides.length + 1}`, bullets: currentBullets });
        currentTitle = '';
        currentBullets = [];
      }
      continue;
    }

    const slideMatch = line.match(/^(?:\*\*)?Slide\s+\d+\s*[:\-–]\s*(.*?)(?:\*\*)?$/i);
    const headingMatch = line.match(/^#{1,3}\s+(.*)$/);
    if (slideMatch || headingMatch) {
      if (currentTitle || currentBullets.length) {
        slides.push({ title: currentTitle || `Slide ${slides.length + 1}`, bullets: currentBullets });
      }
      currentTitle = stripInlineMd((slideMatch ? slideMatch[1] : headingMatch?.[1] || '').trim());
      currentBullets = [];
      continue;
    }

    if (line) {
      currentBullets.push(stripInlineMd(line.replace(/^[-*]\s+/, '• ')));
    }
  }

  if (currentTitle || currentBullets.length) {
    slides.push({ title: currentTitle || 'Meridian Presentation', bullets: currentBullets });
  }
  if (slides.length === 0) {
    slides.push({ title: 'Slide 1', bullets: [stripInlineMd(content)] });
  }
  return slides;
}

interface Props {
  visible: boolean;
  message: Message | null;
  inlinePane?: boolean;
  onClose: () => void;
  onDownload: (messageId: string, format: 'pdf' | 'docx' | 'pptx') => void;
}

export function DocumentPreviewModal({ visible, message, inlinePane = false, onClose, onDownload }: Props) {
  const { palette } = useTheme();
  const [tab, setTab] = useState<PreviewTab>('artifact');
  const [slideIndex, setSlideIndex] = useState(0);
  const [pdfBlobUrl, setPdfBlobUrl] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const slides = useMemo(() => (message ? parseSlidesFromMarkdown(message.content) : []), [message]);

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

  const renderPanelContent = () => (
    <View
      style={[
        inlinePane ? styles.inlineContainer : styles.dialog,
        { backgroundColor: palette.surface, borderColor: palette.border },
      ]}
    >
      {/* Header */}
      <View style={[styles.header, { borderBottomColor: palette.border }]}>
        <View style={styles.tabsRow}>
          {(
            [
              { id: 'artifact', label: 'Artifact', icon: 'sparkles-outline' },
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
              await Clipboard.setStringAsync(message.content);
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
        {tab === 'artifact' ? (
          <ScrollView contentContainerStyle={{ padding: 8 }}>
            <MarkdownRenderer content={message.content} />
          </ScrollView>
        ) : null}

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
                <Text style={styles.paperBody}>{stripInlineMd(message.content)}</Text>
              </View>
            </ScrollView>
          )
        ) : null}

        {tab === 'pptx' && activeSlide ? (
          <View style={styles.slideStage}>
            <View style={styles.slideCard}>
              <View style={styles.slideTopBar} />
              <ScrollView contentContainerStyle={styles.slideInner}>
                <Text style={styles.slideTitle}>{activeSlide.title}</Text>
                <View style={{ gap: 8, marginTop: 14 }}>
                  {activeSlide.bullets.map((b, i) => (
                    <Text key={i} style={styles.slideBullet}>
                      {b}
                    </Text>
                  ))}
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

        {tab === 'docx' ? (
          <ScrollView contentContainerStyle={styles.paperWrap}>
            <View style={styles.paperPage}>
              {message.content.split('\n').map((raw, idx) => {
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
    width: '46%',
    minWidth: 380,
    maxWidth: 660,
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
    maxWidth: 960,
    height: '86%',
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
  slideTopBar: { height: 10, width: '100%', backgroundColor: '#0D9488' },
  slideInner: { padding: 24 },
  slideTitle: { fontSize: 22, fontWeight: '800', color: '#0F172A' },
  slideBullet: { fontSize: 15, lineHeight: 22, color: '#1E293B' },
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
});
