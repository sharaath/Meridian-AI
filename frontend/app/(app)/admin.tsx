import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { AdminOverview } from '@/types/api';

export default function AdminDashboardPage() {
  const { palette } = useTheme();
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    api
      .getAdminOverview()
      .then(setData)
      .catch((err) => setError(err.message || 'Administrator privileges required.'));
  };

  useEffect(() => {
    load();
  }, []);

  const cyclePlan = async (userId: string, current: string) => {
    const order: Array<'free' | 'pro' | 'enterprise'> = ['free', 'pro', 'enterprise'];
    const next = order[(order.indexOf(current as any) + 1) % order.length];
    await api.updateUserPlan(userId, next);
    load();
  };

  if (error) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24, backgroundColor: palette.bg }}>
        <Text style={{ color: palette.danger, fontSize: 16, fontWeight: '600' }}>{error}</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: palette.bg }}>
        <ActivityIndicator size="large" color={palette.accent} />
      </View>
    );
  }

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <Text style={[styles.title, { color: palette.text }]}>Admin Dashboard</Text>

        <View style={styles.grid}>
          {[
            { label: 'Total Users', value: data.metrics.total_users },
            { label: 'Conversations', value: data.metrics.total_conversations },
            { label: 'Messages', value: data.metrics.total_messages },
            { label: 'Files', value: data.metrics.total_files },
            { label: 'Total Tokens', value: data.metrics.total_tokens.toLocaleString() },
            { label: 'Rate Limit Blocks', value: data.metrics.rate_limit_blocked },
          ].map((m, i) => (
            <View key={i} style={[styles.statBox, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Text style={{ fontSize: 20, fontWeight: '800', color: palette.text }}>{m.value}</Text>
              <Text style={{ fontSize: 12, color: palette.textMuted, marginTop: 4 }}>{m.label}</Text>
            </View>
          ))}
        </View>

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.sectionTitle, { color: palette.text }]}>Users & Subscription Plans</Text>
          {data.users.map((u) => (
            <View key={u.id} style={[styles.userRow, { borderBottomColor: palette.border }]}>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '600', color: palette.text }}>{u.username} ({u.role})</Text>
                <Text style={{ fontSize: 12, color: palette.textMuted }}>{u.email}</Text>
              </View>
              <TouchableOpacity
                onPress={() => cyclePlan(u.id, u.subscription_plan)}
                style={[styles.planBadge, { backgroundColor: palette.accentSoft }]}
              >
                <Text style={{ fontSize: 12, fontWeight: '700', color: palette.accent }}>
                  {u.subscription_plan.toUpperCase()}
                </Text>
              </TouchableOpacity>
            </View>
          ))}
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  container: { padding: 20, alignItems: 'center' },
  inner: { width: '100%', maxWidth: 900, gap: 14 },
  title: { fontSize: 24, fontWeight: '700' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  statBox: { minWidth: 140, flex: 1, borderWidth: 1, borderRadius: 14, padding: 14 },
  card: { borderWidth: 1, borderRadius: 14, padding: 16 },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 10 },
  userRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1 },
  planBadge: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8 },
});

