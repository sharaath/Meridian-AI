import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { MemoryItem } from '@/types/api';

export default function MemoryPage() {
  const { palette } = useTheme();
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [newContent, setNewContent] = useState('');
  const [category, setCategory] = useState('preference');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingText, setEditingText] = useState('');

  const loadMemories = async () => {
    const list = await api.listMemories();
    setMemories(list);
  };

  useEffect(() => {
    loadMemories();
  }, []);

  const handleAdd = async () => {
    if (!newContent.trim()) return;
    await api.createMemory(newContent.trim(), category.trim() || 'general');
    setNewContent('');
    await loadMemories();
  };

  const handleSaveEdit = async (id: string) => {
    if (!editingText.trim()) return;
    await api.updateMemory(id, { memory_content: editingText.trim() });
    setEditingId(null);
    await loadMemories();
  };

  const handleDelete = async (id: string) => {
    await api.deleteMemory(id);
    setMemories((prev) => prev.filter((m) => m.id !== id));
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <Text style={[styles.title, { color: palette.text }]}>Memory Management</Text>
        <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>
          Manage what Meridian remembers across your conversations. You have complete control to inspect, edit, or delete any entry.
        </Text>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={{ fontSize: 15, fontWeight: '700', color: palette.text, marginBottom: 8 }}>Add Memory</Text>
          <TextInput
            value={newContent}
            onChangeText={setNewContent}
            placeholder="e.g., I am a mobile engineer using Expo and FastAPI."
            placeholderTextColor={palette.textMuted}
            style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
          />
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <TextInput
              value={category}
              onChangeText={setCategory}
              placeholder="Category"
              placeholderTextColor={palette.textMuted}
              style={[styles.catInput, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
            />
            <TouchableOpacity onPress={handleAdd} style={[styles.addBtn, { backgroundColor: palette.accent }]}>
              <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>Save Memory</Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={{ fontSize: 15, fontWeight: '700', color: palette.text, marginBottom: 10 }}>
            Saved Memories ({memories.length})
          </Text>
          {memories.length === 0 ? (
            <Text style={{ color: palette.textMuted, fontSize: 13.5 }}>No memories stored yet.</Text>
          ) : (
            memories.map((mem) => (
              <View key={mem.id} style={[styles.memRow, { borderBottomColor: palette.border }]}>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 11.5, fontWeight: '700', color: palette.accent, textTransform: 'uppercase' }}>
                    {mem.category}
                  </Text>
                  {editingId === mem.id ? (
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 4 }}>
                      <TextInput
                        value={editingText}
                        onChangeText={setEditingText}
                        style={[styles.input, { flex: 1, marginBottom: 0, color: palette.text, borderColor: palette.accent }]}
                      />
                      <TouchableOpacity onPress={() => handleSaveEdit(mem.id)} style={[styles.addBtn, { backgroundColor: palette.accent }]}>
                        <Text style={{ color: '#FFFFFF', fontWeight: '700' }}>Save</Text>
                      </TouchableOpacity>
                    </View>
                  ) : (
                    <Text style={{ fontSize: 14, color: palette.text, marginTop: 3 }}>{mem.memory_content}</Text>
                  )}
                </View>
                <TouchableOpacity
                  onPress={() => {
                    setEditingId(mem.id);
                    setEditingText(mem.memory_content);
                  }}
                  style={{ padding: 6 }}
                >
                  <Ionicons name="pencil-outline" size={16} color={palette.textMuted} />
                </TouchableOpacity>
                <TouchableOpacity onPress={() => handleDelete(mem.id)} style={{ padding: 6 }}>
                  <Ionicons name="trash-outline" size={16} color={palette.danger} />
                </TouchableOpacity>
              </View>
            ))
          )}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  container: { padding: 20, alignItems: 'center' },
  inner: { width: '100%', maxWidth: 780, gap: 14 },
  title: { fontSize: 24, fontWeight: '700' },
  card: { borderWidth: 1, borderRadius: 14, padding: 16 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14, marginBottom: 10 },
  catInput: { flex: 1, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14 },
  addBtn: { paddingHorizontal: 16, paddingVertical: 11, borderRadius: 10 },
  memRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, gap: 6 },
});

