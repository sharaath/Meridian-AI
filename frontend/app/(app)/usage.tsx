import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { UsageStats } from '@/types/api';

export default function UsagePage() {
  const { palette } = useTheme();
  const [stats, setStats] = useState<UsageStats | null>(null);

  useEffect(() => {
    api.getUsage().then(setStats).catch(() => {});
  }, []);

  if (!stats) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: palette.bg }}>
        <ActivityIndicator size="large" color={palette.accent} />
      </View>
    );
  }

  const msgLimit = stats.daily_limits.messages_limit;
  const tokLimit = stats.daily_limits.tokens_limit;

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <Text style={[styles.title, { color: palette.text }]}>Usage Dashboard</Text>
        <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>
          Current plan: <Text style={{ fontWeight: '700', color: palette.accent }}>{stats.subscription_plan.toUpperCase()}</Text>
        </Text>

        {/* Daily Limits */}
        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Daily Quota</Text>
          <Text style={{ fontSize: 13.5, color: palette.textSecondary, marginBottom: 6 }}>
            Messages today: {stats.daily_limits.messages_used} {msgLimit ? `/ ${msgLimit}` : '(Unlimited)'}
          </Text>
          <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>
            Tokens today: {stats.daily_limits.tokens_used.toLocaleString()} {tokLimit ? `/ ${tokLimit.toLocaleString()}` : '(Unlimited)'}
          </Text>
        </View>

        {/* Summary Metrics */}
        <View style={styles.grid}>
          {[
            { label: '30-Day Tokens', value: stats.thirty_day_summary.total_tokens.toLocaleString() },
            { label: '30-Day Requests', value: String(stats.thirty_day_summary.requests) },
            { label: 'Conversations', value: String(stats.totals.conversations) },
            { label: 'Uploaded Files', value: String(stats.totals.files) },
          ].map((stat, i) => (
            <View key={i} style={[styles.statBox, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Text style={{ fontSize: 22, fontWeight: '800', color: palette.text }}>{stat.value}</Text>
              <Text style={{ fontSize: 12.5, color: palette.textMuted, marginTop: 4 }}>{stat.label}</Text>
            </View>
          ))}
        </View>

        {/* Breakdown by Model */}
        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Usage by Model (30 Days)</Text>
          {stats.by_model.length === 0 ? (
            <Text style={{ fontSize: 13.5, color: palette.textMuted }}>No AI requests recorded yet.</Text>
          ) : (
            stats.by_model.map((row) => (
              <View key={row.model_id} style={[styles.modelRow, { borderBottomColor: palette.border }]}>
                <Text style={{ flex: 1, fontWeight: '600', color: palette.text }}>{row.model_id}</Text>
                <Text style={{ color: palette.textSecondary, marginRight: 16 }}>{row.requests} reqs</Text>
                <Text style={{ fontWeight: '700', color: palette.accent }}>{row.total_tokens.toLocaleString()} tok</Text>
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
  inner: { width: '100%', maxWidth: 820, gap: 14 },
  title: { fontSize: 24, fontWeight: '700' },
  card: { borderWidth: 1, borderRadius: 14, padding: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  statBox: { flex: 1, minWidth: 160, borderWidth: 1, borderRadius: 14, padding: 16 },
  modelRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1 },
});

