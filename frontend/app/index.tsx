import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';

const FEATURES: Array<{ title: string; desc: string; icon: keyof typeof Ionicons.glyphMap }> = [
  {
    title: 'Real-Time Streaming Chat',
    desc: 'Fluid SSE responses with edit-and-resend, regenerate, stop generation, and follow-up prompts.',
    icon: 'chatbubbles-outline',
  },
  {
    title: 'Document Intelligence',
    desc: 'Upload PDF, DOCX, and TXT files with page-level extraction, summaries, and grounded Q&A.',
    icon: 'document-text-outline',
  },
  {
    title: 'Coding & Vision',
    desc: 'Syntax-highlighted code blocks, debugging, and multimodal image, chart, and screenshot analysis.',
    icon: 'code-slash-outline',
  },
  {
    title: 'Voice & Web Search',
    desc: 'Speak naturally with speech-to-text, listen with text-to-speech, and cite live web sources.',
    icon: 'globe-outline',
  },
  {
    title: 'Memory & Workspaces',
    desc: 'Private conversation memory, custom AI instructions, and project workspaces.',
    icon: 'bookmark-outline',
  },
  {
    title: 'Private by Architecture',
    desc: 'Row-level data isolation, encrypted sessions, and zero frontend API keys.',
    icon: 'shield-checkmark-outline',
  },
];

export default function LandingPage() {
  const { palette, isDark, toggleTheme } = useTheme();
  const { user } = useAuth();
  const router = useRouter();

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      {/* Top Navbar */}
      <View style={styles.navbar}>
        <MeridianLogo size={34} />
        <View style={styles.navActions}>
          <TouchableOpacity onPress={toggleTheme} style={[styles.themeBtn, { borderColor: palette.border }]}>
            <Ionicons name={isDark ? 'sunny-outline' : 'moon-outline'} size={18} color={palette.text} />
          </TouchableOpacity>
          {user ? (
            <TouchableOpacity
              onPress={() => router.push('/chat' as never)}
              style={[styles.primaryBtn, { backgroundColor: palette.accent }]}
            >
              <Text style={styles.primaryBtnText}>Open Workspace</Text>
            </TouchableOpacity>
          ) : (
            <>
              <TouchableOpacity
                onPress={() => router.push('/login' as never)}
                style={[styles.outlineBtn, { borderColor: palette.border }]}
              >
                <Text style={{ fontWeight: '600', color: palette.text }}>Sign in</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => router.push('/register' as never)}
                style={[styles.primaryBtn, { backgroundColor: palette.accent }]}
              >
                <Text style={styles.primaryBtnText}>Get started</Text>
              </TouchableOpacity>
            </>
          )}
        </View>
      </View>

      {/* Hero */}
      <View style={styles.hero}>
        <View style={[styles.badge, { backgroundColor: palette.accentSoft }]}>
          <Text style={{ color: palette.accent, fontSize: 12.5, fontWeight: '700' }}>
            CROSS-PLATFORM AI WORKSPACE · WEB & ANDROID
          </Text>
        </View>
        <Text style={[styles.heroTitle, { color: palette.text }]}>
          Think deeper, build faster, and analyze anything with Meridian.
        </Text>
        <Text style={[styles.heroSub, { color: palette.textSecondary }]}>
          A calm, modern AI assistant for real-time reasoning, document intelligence, coding, vision, voice, and live web citations.
        </Text>
        <View style={styles.heroCtas}>
          <TouchableOpacity
            onPress={() => router.push((user ? '/chat' : '/register') as never)}
            style={[styles.ctaLarge, { backgroundColor: palette.accent }]}
          >
            <Text style={styles.ctaLargeText}>{user ? 'Continue to Chat' : 'Create Free Account'}</Text>
            <Ionicons name="arrow-forward" size={18} color="#FFFFFF" />
          </TouchableOpacity>
          {!user ? (
            <TouchableOpacity
              onPress={() => router.push('/login' as never)}
              style={[styles.ctaSecondary, { borderColor: palette.borderStrong, backgroundColor: palette.surface }]}
            >
              <Text style={{ fontSize: 15, fontWeight: '600', color: palette.text }}>Sign in to existing account</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      </View>

      {/* Features Grid */}
      <View style={styles.grid}>
        {FEATURES.map((feat, idx) => (
          <View key={idx} style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[styles.iconBox, { backgroundColor: palette.accentSoft }]}>
              <Ionicons name={feat.icon} size={20} color={palette.accent} />
            </View>
            <Text style={{ fontSize: 16, fontWeight: '700', color: palette.text, marginTop: 12 }}>
              {feat.title}
            </Text>
            <Text style={{ fontSize: 13.5, lineHeight: 20, color: palette.textSecondary, marginTop: 6 }}>
              {feat.desc}
            </Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  container: { alignItems: 'center', paddingHorizontal: 20, paddingTop: 24, paddingBottom: 60 },
  navbar: {
    width: '100%',
    maxWidth: 1080,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 48,
  },
  navActions: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  themeBtn: { width: 38, height: 38, borderRadius: 10, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  outlineBtn: { paddingHorizontal: 14, paddingVertical: 9, borderRadius: 10, borderWidth: 1 },
  primaryBtn: { paddingHorizontal: 16, paddingVertical: 9, borderRadius: 10 },
  primaryBtnText: { color: '#FFFFFF', fontWeight: '700', fontSize: 14 },
  hero: { width: '100%', maxWidth: 800, alignItems: 'center', marginBottom: 48 },
  badge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, marginBottom: 18 },
  heroTitle: { fontSize: 38, fontWeight: '800', textAlign: 'center', letterSpacing: -1, lineHeight: 46 },
  heroSub: { fontSize: 16.5, textAlign: 'center', lineHeight: 25, marginTop: 16, maxWidth: 620 },
  heroCtas: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginTop: 28, justifyContent: 'center' },
  ctaLarge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 22,
    paddingVertical: 14,
    borderRadius: 12,
  },
  ctaLargeText: { color: '#FFFFFF', fontSize: 15.5, fontWeight: '700' },
  ctaSecondary: { paddingHorizontal: 20, paddingVertical: 14, borderRadius: 12, borderWidth: 1 },
  grid: {
    width: '100%',
    maxWidth: 1080,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
    justifyContent: 'center',
  },
  card: { width: '31%', minWidth: 270, borderRadius: 16, borderWidth: 1, padding: 20 },
  iconBox: { width: 40, height: 40, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
});

