import React, { useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';

export default function RegisterPage() {
  const { palette } = useTheme();
  const { register } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRegister = async () => {
    if (!username.trim() || !email.trim() || password.length < 8) {
      setError('Enter a username, valid email, and a password of at least 8 characters.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await register(email.trim(), username.trim(), password);
      router.replace('/chat' as never);
    } catch (err: any) {
      setError(err.message || 'Registration failed.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.center}>
      <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <View style={{ alignItems: 'center', marginBottom: 20 }}>
          <MeridianLogo size={38} />
          <Text style={{ fontSize: 22, fontWeight: '700', color: palette.text, marginTop: 14 }}>
            Create your account
          </Text>
          <Text style={{ fontSize: 13.5, color: palette.textMuted, marginTop: 4 }}>
            Private conversations, memory, and document intelligence
          </Text>
        </View>

        {error ? (
          <View style={[styles.errBox, { backgroundColor: palette.dangerSoft, borderColor: palette.danger }]}>
            <Text style={{ color: palette.danger, fontSize: 13 }}>{error}</Text>
          </View>
        ) : null}

        <Text style={[styles.label, { color: palette.textSecondary }]}>Username</Text>
        <TextInput
          value={username}
          onChangeText={setUsername}
          placeholder="Your display name"
          placeholderTextColor={palette.textMuted}
          style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
        />

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

        <Text style={[styles.label, { color: palette.textSecondary }]}>Password (min. 8 characters)</Text>
        <TextInput
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          placeholder="Create a strong password"
          placeholderTextColor={palette.textMuted}
          onSubmitEditing={handleRegister}
          style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
        />

        <TouchableOpacity
          onPress={handleRegister}
          disabled={submitting}
          style={[styles.primaryBtn, { backgroundColor: palette.accent }]}
        >
          {submitting ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryBtnText}>Create account</Text>}
        </TouchableOpacity>

        <View style={styles.footerRow}>
          <Text style={{ fontSize: 13.5, color: palette.textSecondary }}>Already have an account? </Text>
          <TouchableOpacity onPress={() => router.push('/login' as never)}>
            <Text style={{ fontSize: 13.5, fontWeight: '700', color: palette.accent }}>Sign in</Text>
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
  primaryBtn: { paddingVertical: 13, borderRadius: 11, alignItems: 'center', marginBottom: 16 },
  primaryBtnText: { color: '#FFFFFF', fontSize: 15, fontWeight: '700' },
  footerRow: { flexDirection: 'row', justifyContent: 'center' },
});

