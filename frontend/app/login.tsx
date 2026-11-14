import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';
import { createAndStorePkce } from '@/utils/pkce';

export default function LoginPage() {
  const { palette } = useTheme();
  const { user, loading, login } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && user) {
      router.replace('/(app)/chat' as never);
    }
  }, [user, loading, router]);

  const handleLogin = async () => {
    if (!email.trim() || !password) {
      setError('Please enter your email and password.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await login(email.trim(), password);
      router.replace('/(app)/chat' as never);
    } catch (err: any) {
      setError(err.message || 'Sign in failed.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setError(null);
    setGoogleLoading(true);
    try {
      const redirectTo =
        Platform.OS === 'web' && typeof window !== 'undefined' ? `${window.location.origin}/login` : 'meridian://chat';

      // Direct Supabase authorize URL for implicit grant (returns token in URL hash without PKCE code verifier requirement)
      const targetUrl = `https://ocqnzkjcffaicqhymwvm.supabase.co/auth/v1/authorize?provider=google&redirect_to=${encodeURIComponent(redirectTo)}`;

      if (Platform.OS === 'web' && typeof window !== 'undefined') {
        window.location.assign(targetUrl);
      } else {
        await Linking.openURL(targetUrl);
      }
    } catch (err: any) {
      setError(err.message || 'Google Sign-In failed.');
      setGoogleLoading(false);
    }
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.center}>
      <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <View style={{ alignItems: 'center', marginBottom: 20 }}>
          <MeridianLogo size={38} />
          <Text style={{ fontSize: 22, fontWeight: '700', color: palette.text, marginTop: 14 }}>
            Welcome back
          </Text>
          <Text style={{ fontSize: 13.5, color: palette.textMuted, marginTop: 4 }}>
            Sign in to your Meridian AI workspace
          </Text>
        </View>

        {error ? (
          <View style={[styles.errBox, { backgroundColor: palette.dangerSoft, borderColor: palette.danger }]}>
            <Text style={{ color: palette.danger, fontSize: 13 }}>{error}</Text>
          </View>
        ) : null}

        <Text style={[styles.label, { color: palette.textSecondary }]}>Email</Text>
        <TextInput
          value={email}
          onChangeText={setEmail}
          autoCapitalize="none"
          keyboardType="email-address"
          placeholder="you@example.com"
          placeholderTextColor={palette.textMuted}
          style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
        />

        <Text style={[styles.label, { color: palette.textSecondary }]}>Password</Text>
        <TextInput
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="Enter your password"
          placeholderTextColor={palette.textMuted}
          onSubmitEditing={handleLogin}
          style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
        />

        <TouchableOpacity onPress={() => router.push('/forgot-password' as never)} style={{ alignSelf: 'flex-end', marginBottom: 16 }}>
          <Text style={{ fontSize: 13, fontWeight: '600', color: palette.accent }}>Forgot password?</Text>
        </TouchableOpacity>

        <TouchableOpacity
          onPress={handleLogin}
          disabled={submitting}
          style={[styles.primaryBtn, { backgroundColor: palette.accent }]}
        >
          {submitting ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryBtnText}>Sign in</Text>}
        </TouchableOpacity>

        <TouchableOpacity
          onPress={handleGoogleSignIn}
          disabled={googleLoading || submitting}
          style={[styles.googleBtn, { borderColor: palette.border, backgroundColor: palette.bg }]}
        >
          {googleLoading ? (
            <ActivityIndicator size="small" color={palette.accent} />
          ) : (
            <>
              <Ionicons name="logo-google" size={17} color={palette.text} />
              <Text style={{ fontSize: 14, fontWeight: '600', color: palette.text }}>Continue with Google</Text>
            </>
          )}
        </TouchableOpacity>

        <View style={styles.footerRow}>
          <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>New to Meridian? </Text>
          <TouchableOpacity onPress={() => router.push('/register' as never)}>
            <Text style={{ fontSize: 13.5, fontWeight: '700', color: palette.accent }}>Create an account</Text>
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  center: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  card: { width: '100%', maxWidth: 420, borderRadius: 18, borderWidth: 1, padding: 26 },
  errBox: { borderWidth: 1, borderRadius: 10, padding: 10, marginBottom: 14 },
  label: { fontSize: 13, fontWeight: '600', marginBottom: 6 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, fontSize: 14.5, marginBottom: 14 },
  primaryBtn: { paddingVertical: 13, borderRadius: 11, alignItems: 'center', marginBottom: 10 },
  primaryBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
  googleBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 12,
    borderRadius: 11,
    borderWidth: 1,
    marginBottom: 16,
  },
  footerRow: { flexDirection: 'row', justifyContent: 'center' },
});

