import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { api } from '@/services/api';

export default function ProfilePage() {
  const { palette } = useTheme();
  const { user, refreshUser, logout } = useAuth();
  const router = useRouter();

  const [username, setUsername] = useState(user?.username || '');
  const [verifyToken, setVerifyToken] = useState('');
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSaveProfile = async () => {
    setError(null);
    setNotice(null);
    try {
      await api.updateProfile(username.trim());
      await refreshUser();
      setNotice('Profile updated.');
    } catch (err: any) {
      setError(err.message || 'Update failed.');
    }
  };

  const handleRequestVerification = async () => {
    setError(null);
    try {
      const res = await api.requestEmailVerification();
      if (res.dev_verification_token) {
        setVerifyToken(res.dev_verification_token);
        setNotice(`Dev verification token generated: ${res.dev_verification_token}`);
      } else {
        setNotice('Verification instructions issued.');
      }
    } catch (err: any) {
      setError(err.message || 'Verification request failed.');
    }
  };

  const handleConfirmVerification = async () => {
    setError(null);
    try {
      await api.confirmEmailVerification(verifyToken.trim());
      await refreshUser();
      setNotice('Email verified successfully.');
      setVerifyToken('');
    } catch (err: any) {
      setError(err.message || 'Invalid verification token.');
    }
  };

  return (
    <ScrollView style={[styles.root, { backgroundColor: palette.bg }]} contentContainerStyle={styles.container}>
      <View style={styles.inner}>
        <Text style={[styles.title, { color: palette.text }]}>Profile</Text>

        {notice ? <Text style={{ color: palette.success, fontSize: 13.5 }}>{notice}</Text> : null}
        {error ? <Text style={{ color: palette.danger, fontSize: 13.5 }}>{error}</Text> : null}

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
          <Text style={[styles.label, { color: palette.textSecondary }]}>Email</Text>
          <Text style={{ fontSize: 15, color: palette.text, marginBottom: 14 }}>
            {user?.email} ({user?.email_verified ? 'Verified' : 'Unverified'})
          </Text>

          <Text style={[styles.label, { color: palette.textSecondary }]}>Username</Text>
          <TextInput
            value={username}
            onChangeText={setUsername}
            style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg }]}
          />

          <TouchableOpacity onPress={handleSaveProfile} style={[styles.btn, { backgroundColor: palette.accent }]}>
            <Text style={styles.btnText}>Save Profile</Text>
          </TouchableOpacity>
        </View>

        {!user?.email_verified ? (
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={{ fontSize: 16, fontWeight: '700', color: palette.text, marginBottom: 8 }}>
              Email Verification
            </Text>
            <TouchableOpacity onPress={handleRequestVerification} style={[styles.outlineBtn, { borderColor: palette.accent }]}>
              <Text style={{ color: palette.accent, fontWeight: '600' }}>Request Verification Token</Text>
            </TouchableOpacity>
            <TextInput
              value={verifyToken}
              onChangeText={setVerifyToken}
              placeholder="Paste verification token"
              placeholderTextColor={palette.textMuted}
              style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.bg, marginTop: 10 }]}
            />
            <TouchableOpacity onPress={handleConfirmVerification} style={[styles.btn, { backgroundColor: palette.accent }]}>
              <Text style={styles.btnText}>Verify Email</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, gap: 10 }]}>
          <TouchableOpacity onPress={() => router.push('/forgot-password' as never)} style={[styles.outlineBtn, { borderColor: palette.border }]}>
            <Text style={{ color: palette.text, fontWeight: '600' }}>Change / Reset Password</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={async () => {
              await logout();
              router.replace('/login' as never);
            }}
            style={[styles.outlineBtn, { borderColor: palette.danger }]}
          >
            <Text style={{ color: palette.danger, fontWeight: '700' }}>Sign Out</Text>
          </TouchableOpacity>
        </View>
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
  label: { fontSize: 13, fontWeight: '600', marginBottom: 6 },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10, fontSize: 14.5, marginBottom: 12 },
  btn: { paddingVertical: 11, paddingHorizontal: 16, borderRadius: 10, alignItems: 'center' },
  btnText: { color: '#FFFFFF', fontWeight: '700' },
  outlineBtn: { paddingVertical: 11, paddingHorizontal: 16, borderRadius: 10, borderWidth: 1, alignItems: 'center' },
});

