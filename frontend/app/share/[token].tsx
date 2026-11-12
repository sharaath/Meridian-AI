import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { MarkdownRenderer } from '@/components/MarkdownRenderer';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { Message } from '@/types/api';

export default function SharedConversationPage() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const { palette } = useTheme();
  const [data, setData] = useState<{ title: string; mode: string; messages: Message[] } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api
      .viewShared(token)
      .then(setData)
      .catch((err) => setError(err.message || 'Shared link not found or revoked.'));
  }, [token]);

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.header}>
        <MeridianLogo size={30} />
        <Text style={{ fontSize: 12, color: palette.textMuted }}>Shared Snapshot</Text>
      </View>

      {error ? (
        <Text style={{ color: palette.danger, fontSize: 15, marginTop: 40 }}>{error}</Text>
      ) : !data ? (
        <ActivityIndicator size="large" color={palette.accent} style={{ marginTop: 40 }} />
      ) : (
        <View style={styles.body}>
          <Text style={{ fontSize: 24, fontWeight: '700', color: palette.text, marginBottom: 16 }}>
            {data.title}
          </Text>
          {data.messages.map((m) => (
            <View
              key={m.id}
              style={[
                styles.card,
                {
                  backgroundColor: m.role === 'user' ? palette.userBubble : palette.surface,
                  borderColor: palette.border,
                },
              ]}
            >
              <Text style={{ fontSize: 12, fontWeight: '700', color: m.role === 'user' ? '#CCFBF1' : palette.accent, marginBottom: 6 }}>
                {m.role === 'user' ? 'User' : 'Meridian'}
              </Text>
              {m.role === 'user' ? (
                <Text style={{ color: palette.userBubbleText, fontSize: 15 }}>{m.content}</Text>
              ) : (
                <MarkdownRenderer content={m.content} />
              )}
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  container: { alignItems: 'center', padding: 20 },
  header: { width: '100%', maxWidth: 820, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 },
  body: { width: '100%', maxWidth: 820, gap: 12 },
  card: { borderRadius: 14, borderWidth: 1, padding: 16 },
});

