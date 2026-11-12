import React, { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { AIModelInfo, ProviderStatus } from '@/types/api';

export default function ModelsPage() {
  const { palette } = useTheme();
  const [models, setModels] = useState<AIModelInfo[]>([]);
  const [providers, setProviders] = useState<ProviderStatus[]>([]);
  const [preferredModel, setPreferredModel] = useState('');
  const [temperature, setTemperature] = useState('0.7');
  const [maxTokens, setMaxTokens] = useState('4096');
  const [topP, setTopP] = useState('0.95');
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  useEffect(() => {
    api.listModelCatalog().then((res) => {
      setModels(res.models);
      setProviders(res.providers);
    });
    api.getPreferences().then((p) => {
      setPreferredModel(p.preferred_model || '');
      const s = p.settings || {};
      if (s.temperature !== undefined) setTemperature(String(s.temperature));
      if (s.max_tokens !== undefined) setMaxTokens(String(s.max_tokens));
      if (s.top_p !== undefined) setTopP(String(s.top_p));
    });
  }, []);

  const handleSave = async () => {
    setSavedMsg(null);
    await api.updatePreferences({
      preferred_model: preferredModel,
      settings: {
        temperature: Math.min(2, Math.max(0, parseFloat(temperature) || 0.7)),
        max_tokens: Math.min(32768, Math.max(64, parseInt(maxTokens, 10) || 4096)),
        top_p: Math.min(1, Math.max(0, parseFloat(topP) || 0.95)),
      },
    });
    setSavedMsg('Model configuration saved.');
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <Text style={[styles.title, { color: palette.text }]}>Model Settings</Text>
        <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>
          Only providers with valid server-side API keys are selectable. Unconfigured models are clearly marked.
        </Text>
        {savedMsg ? <Text style={{ color: palette.success, fontSize: 13.5 }}>{savedMsg}</Text> : null}

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Provider Connection Status</Text>
          {providers.map((p) => (
            <View key={p.provider} style={[styles.providerRow, { borderBottomColor: palette.border }]}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontSize: 14.5, fontWeight: '700', color: palette.text, textTransform: 'capitalize' }}>
                  {p.provider}
                </Text>
                <Text style={{ fontSize: 12, color: palette.textMuted }}>
                  Env variable: {p.required_env_var}
                </Text>
              </View>
              <View
                style={[
                  styles.statusBadge,
                  { backgroundColor: p.configured ? palette.accentSoft : palette.dangerSoft },
                ]}
              >
                <Text style={{ fontSize: 12, fontWeight: '700', color: p.configured ? palette.accent : palette.danger }}>
                  {p.configured ? 'Connected' : 'Not Configured'}
                </Text>
              </View>
            </View>
          ))}
        </View>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Available Models</Text>
          {models.map((m) => {
            const active = preferredModel === m.id;
            return (
              <TouchableOpacity
                key={m.id}
                disabled={!m.configured}
                onPress={() => setPreferredModel(m.id)}
                style={[
                  styles.modelRow,
                  {
                    opacity: m.configured ? 1 : 0.55,
                    borderColor: active ? palette.accent : palette.border,
                    backgroundColor: active ? palette.accentSoft : palette.bg,
                  },
                ]}
              >
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14.5, fontWeight: '700', color: palette.text }}>
                    {m.name} {!m.configured ? `(Requires ${m.required_env_var})` : ''}
                  </Text>
                  <Text style={{ fontSize: 12, color: palette.textMuted }}>{m.description}</Text>
                </View>
                {active ? <Ionicons name="checkmark-circle" size={18} color={palette.accent} /> : null}
              </TouchableOpacity>
            );
          })}
        </View>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Generation Parameters</Text>
          <View style={styles.paramRow}>
            <View style={{ flex: 1 }}>
              <Text style={[styles.label, { color: palette.textSecondary }]}>Temperature (0.0 – 2.0)</Text>
              <TextInput
                value={temperature}
                onChangeText={setTemperature}
                keyboardType="decimal-pad"
                style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.label, { color: palette.textSecondary }]}>Max Output Tokens</Text>
              <TextInput
                value={maxTokens}
                onChangeText={setMaxTokens}
                keyboardType="number-pad"
                style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.label, { color: palette.textSecondary }]}>Top-P (0.0 – 1.0)</Text>
              <TextInput
                value={topP}
                onChangeText={setTopP}
                keyboardType="decimal-pad"
                style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
              />
            </View>
          </View>
        </View>

        <TouchableOpacity onPress={handleSave} style={[styles.saveBtn, { backgroundColor: palette.accent }]}>
          <Text style={{ color: '#FFFFFF', fontWeight: '700', fontSize: 15 }}>Save Model Configuration</Text>
        </TouchableOpacity>
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
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 10 },
  providerRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999 },
  modelRow: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: 12, padding: 12, marginBottom: 8 },
  paramRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  label: { fontSize: 12.5, fontWeight: '600', marginBottom: 6 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 9, fontSize: 14 },
  saveBtn: { paddingVertical: 13, borderRadius: 12, alignItems: 'center' },
});

