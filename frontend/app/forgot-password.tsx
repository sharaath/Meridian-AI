import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import { MeridianLogo } from '@/components/MeridianLogo';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';

export default function ForgotPasswordPage() {
  const { palette } = useTheme();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [step, setStep] = useState<'request' | 'confirm'>('request');
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRequest = async () => {
    setError(null);
    setStatusMsg(null);
    try {
      const res = await api.requestPasswordReset(email.trim());
      setStatusMsg(
        res.dev_reset_token
          ? `Reset token issued (dev mode): ${res.dev_reset_token}`
          : res.message
      );
      if (res.dev_reset_token) setToken(res.dev_reset_token);
      setStep('confirm');
    } catch (err: any) {
      setError(err.message || 'Failed to request reset.');
    }
  };

  const handleConfirm = async () => {
    setError(null);
    try {
      await api.confirmPasswordReset(token.trim(), newPassword);
      router.replace('/login' as never);
    } catch (err: any) {
      setError(err.message || 'Password reset failed.');
    }
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.center}>
      <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
        <View style={{ alignItems: 'center', marginBottom: 18 }}>
          <MeridianLogo size={34} />
          <Text style={{ fontSize: 20, fontWeight: '700', color: palette.text, marginTop: 12 }}>
            Reset Password
          </Text>
        </View>

        {error ? <Text style={{ color: palette.danger, marginBottom: 12, fontSize: 13 }}>{error}</Text> : null}
        {statusMsg ? <Text style={{ color: palette.success, marginBottom: 12, fontSize: 13 }}>{statusMsg}</Text> : null}

        {step === 'request' ? (
          <>
            <TextInput
              value={email}
              onChangeText={setEmail}
              placeholder="Account email"
              autoCapitalize="none"
              placeholderTextColor={palette.textMuted}
              style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
            />
            <TouchableOpacity onPress={handleRequest} style={[styles.btn, { backgroundColor: palette.accent }]}>
              <Text style={styles.btnText}>Send reset instructions</Text>
            </TouchableOpacity>
          </>
        ) : (
          <>
            <TextInput
              value={token}
              onChangeText={setToken}
              placeholder="Reset token"
              placeholderTextColor={palette.textMuted}
              style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
            />
            <TextInput
              value={newPassword}
              onChangeText={setNewPassword}
              secureTextEntry
              placeholder="New password (min 8 chars)"
              placeholderTextColor={palette.textMuted}
              style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
            />
            <TouchableOpacity onPress={handleConfirm} style={[styles.btn, { backgroundColor: palette.accent }]}>
              <Text style={styles.btnText}>Update password</Text>
            </TouchableOpacity>
          </>
        )}

        <TouchableOpacity onPress={() => router.replace('/login' as never)} style={{ alignItems: 'center', marginTop: 10 }}>
          <Text style={{ color: palette.accent, fontWeight: '600', fontSize: 13.5 }}>Back to sign in</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  center: { flexGrow: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  card: { width: '100%', maxWidth: 420, borderRadius: 18, borderWidth: 1, padding: 24 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11, fontSize: 14, marginBottom: 12 },
  btn: { paddingVertical: 13, borderRadius: 11, alignItems: 'center' },
  btnText: { color: '#FFFFFF', fontWeight: '700', fontSize: 14.5 },
});

