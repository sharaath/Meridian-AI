import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { ThemePreference, useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';

export default function SettingsPage() {
  const { palette, preference, setThemePreference } = useTheme();
  const [customInstructions, setCustomInstructions] = useState('');
  const [memoryEnabled, setMemoryEnabled] = useState(true);
  const [webSearchDefault, setWebSearchDefault] = useState(false);
  const [voiceAutoPlay, setVoiceAutoPlay] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  useEffect(() => {
    api.getPreferences().then((p) => {
      setCustomInstructions(p.custom_instructions || '');
      setMemoryEnabled(p.memory_enabled);
      setWebSearchDefault(p.web_search_enabled);
      setVoiceAutoPlay(p.voice_auto_play);
    });
  }, []);

  const handleSave = async () => {
    setSavedMsg(null);
    await api.updatePreferences({
      theme: preference,
      custom_instructions: customInstructions,
      memory_enabled: memoryEnabled,
      web_search_enabled: webSearchDefault,
      voice_auto_play: voiceAutoPlay,
    });
    setSavedMsg('Settings saved.');
  };

  const themes: ThemePreference[] = ['light', 'dark', 'system'];

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <Text style={[styles.title, { color: palette.text }]}>Settings</Text>
        {savedMsg ? <Text style={{ color: palette.success, fontSize: 13.5 }}>{savedMsg}</Text> : null}

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Appearance</Text>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            {themes.map((t) => {
              const active = preference === t;
              return (
                <TouchableOpacity
                  key={t}
                  onPress={() => setThemePreference(t)}
                  style={[
                    styles.pill,
                    {
                      borderColor: active ? palette.accent : palette.border,
                      backgroundColor: active ? palette.accentSoft : palette.bg,
                    },
                  ]}
                >
                  <Text style={{ fontWeight: '600', color: active ? palette.accent : palette.textSecondary, textTransform: 'capitalize' }}>
                    {t}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Custom AI Instructions</Text>
          <Text style={{ fontSize: 13, color: palette.textMuted, marginBottom: 8 }}>
            Applied automatically across your Meridian conversations.
          </Text>
          <TextInput
            value={customInstructions}
            onChangeText={setCustomInstructions}
            placeholder="e.g., Prefer TypeScript examples, concise bullet points, and explain trade-offs."
            placeholderTextColor={palette.textMuted}
            multiline
            style={[styles.textarea, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
          />
        </View>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, gap: 14 }]}>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 15, fontWeight: '600', color: palette.text }}>Conversation Memory</Text>
              <Text style={{ fontSize: 12.5, color: palette.textMuted }}>Allow Meridian to use your saved memories.</Text>
            </View>
            <Switch value={memoryEnabled} onValueChange={setMemoryEnabled} />
          </View>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 15, fontWeight: '600', color: palette.text }}>Web Search Default</Text>
              <Text style={{ fontSize: 12.5, color: palette.textMuted }}>Enable live web citations by default.</Text>
            </View>
            <Switch value={webSearchDefault} onValueChange={setWebSearchDefault} />
          </View>
          <View style={styles.switchRow}>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 15, fontWeight: '600', color: palette.text }}>Voice Auto-Play</Text>
              <Text style={{ fontSize: 12.5, color: palette.textMuted }}>Speak responses automatically when ready.</Text>
            </View>
            <Switch value={voiceAutoPlay} onValueChange={setVoiceAutoPlay} />
          </View>
        </View>

        <TouchableOpacity onPress={handleSave} style={[styles.saveBtn, { backgroundColor: palette.accent }]}>
          <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 15 }}>Save Preferences</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  container: { padding: 20, alignItems: 'center' },
  inner: { width: '100%', maxWidth: 680, gap: 14 },
  title: { fontSize: 24, fontWeight: '700' },
  card: { borderWidth: 1, borderRadius: 14, padding: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 10 },
  pill: { paddingHorizontal: 16, paddingVertical: 9, borderRadius: 10, borderWidth: 1 },
  textarea: { borderWidth: 1, borderRadius: 10, padding: 12, minHeight: 100, textAlignVertical: 'top', fontSize: 14 },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  saveBtn: { paddingVertical: 13, borderRadius: 12, alignItems: 'center' },
});

