import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';
import { Ionicons } from '@expo/vector-icons';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { useChat } from '@/contexts/ChatContext';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { UploadedFile } from '@/types/api';

export default function DocumentsPage() {
  const { palette } = useTheme();
  const { defaultModel } = useChat();

  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [previewFile, setPreviewFile] = useState<UploadedFile | null>(null);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<string | null>(null);
  const [refs, setRefs] = useState<Array<{ file_id: string; filename: string; page_count: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadFiles = async () => {
    setLoading(true);
    try {
      const list = await api.listFiles('document');
      setFiles(list);
    } catch (err: any) {
      setError(err.message || 'Failed to load documents.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadFiles();
  }, []);

  const handleUpload = async () => {
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
      setUploading(true);
      setError(null);
      const uploaded = await api.uploadFile({
        uri: asset.uri,
        name: asset.name,
        type: asset.mimeType || 'application/octet-stream',
        webFile: (asset as any).file,
      });
      setFiles((prev) => [uploaded, ...prev]);
      setSelectedIds((prev) => [...prev, uploaded.id]);
      setPreviewFile(uploaded);
    } catch (err: any) {
      setError(err.message || 'Upload failed.');
    } finally {
      setUploading(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const handlePreview = async (id: string) => {
    try {
      const detail = await api.getFileDetail(id);
      setPreviewFile(detail);
    } catch (err: any) {
      setError(err.message || 'Could not load document text.');
    }
  };

  const handleDelete = async (id: string) => {
    await api.deleteFile(id);
    setFiles((prev) => prev.filter((f) => f.id !== id));
    setSelectedIds((prev) => prev.filter((x) => x !== id));
    if (previewFile?.id === id) setPreviewFile(null);
  };

  const runAnalysis = async (customPrompt?: string) => {
    if (selectedIds.length === 0) {
      setError('Select one or more documents first.');
      return;
    }
    const q = (customPrompt || question).trim() || 'Summarize the selected documents with page references.';
    setAnalyzing(true);
    setError(null);
    try {
      const res = await api.analyzeDocuments(selectedIds, q, defaultModel);
      setAnswer(res.answer);
      setRefs(res.references);
    } catch (err: any) {
      setError(err.message || 'Document analysis failed.');
    } finally {
      setAnalyzing(false);
    }
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <View style={styles.headerRow}>
          <View>
            <Text style={[styles.title, { color: palette.text }]}>Document Intelligence</Text>
            <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>
              Upload PDF, DOCX, TXT, MD, or CSV files for page-referenced summaries and Q&A.
            </Text>
          </View>
          <TouchableOpacity onPress={handleUpload} disabled={uploading} style={[styles.uploadBtn, { backgroundColor: palette.accent }]}>
            {uploading ? <ActivityIndicator color="#FFFFFF" size="small" /> : <Ionicons name="cloud-upload-outline" size={17} color="#FFFFFF" />}
            <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 13.5 }}>Upload Document</Text>
          </TouchableOpacity>
        </View>

        {error ? (
          <View style={[styles.errBox, { backgroundColor: palette.dangerSoft, borderColor: palette.danger }]}>
            <Text style={{ color: palette.danger, fontSize: 13 }}>{error}</Text>
          </View>
        ) : null}

        {/* Uploaded Documents List */}
        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.cardTitle, { color: palette.text }]}>Your Documents ({files.length})</Text>
          {loading ? (
            <ActivityIndicator color={palette.accent} />
          ) : files.length === 0 ? (
            <Text style={{ color: palette.textMuted, fontSize: 13.5 }}>No documents uploaded yet.</Text>
          ) : (
            files.map((f) => {
              const checked = selectedIds.includes(f.id);
              return (
                <View key={f.id} style={[styles.fileRow, { borderBottomColor: palette.border }]}>
                  <TouchableOpacity onPress={() => toggleSelect(f.id)} style={{ paddingRight: 8 }}>
                    <Ionicons
                      name={checked ? 'checkbox' : 'square-outline'}
                      size={20}
                      color={checked ? palette.accent : palette.textMuted}
                    />
                  </TouchableOpacity>
                  <TouchableOpacity style={{ flex: 1 }} onPress={() => handlePreview(f.id)}>
                    <Text style={{ fontSize: 14, fontWeight: '600', color: palette.text }}>{f.filename}</Text>
                    <Text style={{ fontSize: 12, color: palette.textMuted }}>
                      Status: {f.processing_status} · {f.page_count} page(s) · {(f.file_size / 1024).toFixed(1)} KB
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handlePreview(f.id)} style={{ paddingHorizontal: 8 }}>
                    <Text style={{ fontSize: 12.5, fontWeight: '600', color: palette.accent }}>Inspect</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => handleDelete(f.id)}>
                    <Ionicons name="trash-outline" size={17} color={palette.danger} />
                  </TouchableOpacity>
                </View>
              );
            })
          )}
        </View>

        {/* Q&A / Summarization Box */}
        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.cardTitle, { color: palette.text }]}>
            Ask or Summarize Selected ({selectedIds.length})
          </Text>
          <TextInput
            value={question}
            onChangeText={setQuestion}
            placeholder="Ask a question across the selected documents..."
            placeholderTextColor={palette.textMuted}
            multiline
            style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
          />
          <View style={{ flexDirection: 'row', gap: 10, flexWrap: 'wrap' }}>
            <TouchableOpacity onPress={() => runAnalysis()} disabled={analyzing} style={[styles.actionBtn, { backgroundColor: palette.accent }]}>
              {analyzing ? <ActivityIndicator color="#FFFFFF" size="small" /> : null}
              <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 13.5 }}>Ask Documents</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => runAnalysis('Summarize the key points, findings, and action items with page references.')}
              disabled={analyzing}
              style={[styles.actionBtn, { borderColor: palette.border, borderWidth: 1 }]}
            >
              <Text style={{ color: palette.text, fontWeight: '600', fontSize: 13.5 }}>Summarize All Selected</Text>
            </TouchableOpacity>
          </View>

          {answer ? (
            <View style={[styles.answerBox, { borderTopColor: palette.border }]}>
              <MarkdownRenderer content={answer} />
              {refs.length > 0 ? (
                <Text style={{ fontSize: 12, color: palette.textMuted, marginTop: 10 }}>
                  Sources: {refs.map((r) => `${r.filename} (${r.page_count}p)`).join(', ')}
                </Text>
              ) : null}
            </View>
          ) : null}
        </View>

        {/* Extracted Text Preview */}
        {previewFile ? (
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={[styles.cardTitle, { color: palette.text }]}>
              Extracted Text: {previewFile.filename}
            </Text>
            <ScrollView style={{ maxHeight: 280 }}>
              <Text selectable style={{ fontSize: 13, lineHeight: 20, color: palette.textSecondary }}>
                {previewFile.extracted_text || 'No extractable text found.'}
              </Text>
            </ScrollView>
          </View>
        ) : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  container: { padding: 20, alignItems: 'center' },
  inner: { width: '100%', maxWidth: 900, gap: 16 },
  headerRow: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  title: { fontSize: 24, fontWeight: '700' },
  uploadBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 11 },
  errBox: { borderWidth: 1, borderRadius: 10, padding: 10 },
  card: { borderWidth: 1, borderRadius: 14, padding: 16 },
  cardTitle: { fontSize: 16, fontWeight: '700', marginBottom: 12 },
  fileRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1 },
  input: { borderWidth: 1, borderRadius: 10, padding: 12, minHeight: 72, textAlignVertical: 'top', marginBottom: 10 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10 },
  answerBox: { marginTop: 16, paddingTop: 14, borderTopWidth: 1 },
});

