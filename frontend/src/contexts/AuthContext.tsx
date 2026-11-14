import React, { createContext, useContext, useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { api, setApiToken } from '@/services/api';
import { UserSummary } from '@/types/api';

const TOKEN_STORAGE_KEY = 'meridian_auth_token';

interface AuthContextValue {
  user: UserSummary | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<string | null>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  loading: true,
  login: async () => {},
  register: async () => null,
  logout: async () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserSummary | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        let activeToken: string | null = null;
        let incomingUser: UserSummary | null = null;

        // Check if returning from OAuth redirect with access_token or code in URL
        if (typeof window !== 'undefined' && window.location) {
          const hash = window.location.hash || '';
          const search = window.location.search || '';

          if (hash.includes('access_token=')) {
            const params = new URLSearchParams(hash.replace(/^#/, ''));
            activeToken = params.get('access_token');
          } else if (search.includes('access_token=')) {
            const params = new URLSearchParams(search.replace(/^\?/, ''));
            activeToken = params.get('access_token');
          } else if (search.includes('code=')) {
            const params = new URLSearchParams(search.replace(/^\?/, ''));
            const code = params.get('code');
            if (code) {
              try {
                const exchange = await api.exchangeOAuthCode(code);
                activeToken = exchange.access_token;
                incomingUser = exchange.user;
              } catch (exchangeErr) {
                console.warn('OAuth code exchange failed:', exchangeErr);
              }
              window.history.replaceState(null, '', window.location.pathname);
            }
          }

          if (activeToken) {
            await AsyncStorage.setItem(TOKEN_STORAGE_KEY, activeToken);
            window.history.replaceState(null, '', window.location.pathname);
          }
        }

        if (!activeToken) {
          activeToken = await AsyncStorage.getItem(TOKEN_STORAGE_KEY);
        }

        if (activeToken) {
          setApiToken(activeToken);
          setToken(activeToken);
          if (incomingUser) {
            setUser(incomingUser);
          } else {
            const profile = await api.me();
            setUser(profile);
          }
        }
      } catch {
        setApiToken(null);
        setToken(null);
        setUser(null);
        await AsyncStorage.removeItem(TOKEN_STORAGE_KEY).catch(() => {});
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password);
    setApiToken(res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    await AsyncStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
  };

  const register = async (email: string, username: string, password: string): Promise<string | null> => {
    const res = await api.register(email, username, password);
    setApiToken(res.access_token);
    setToken(res.access_token);
    setUser(res.user);
    await AsyncStorage.setItem(TOKEN_STORAGE_KEY, res.access_token);
    return res.verification_notice || null;
  };

  const logout = async () => {
    try {
      await api.logout();
    } catch {
      // Ignore network errors during logout
    }
    setApiToken(null);
    setToken(null);
    setUser(null);
    await AsyncStorage.removeItem(TOKEN_STORAGE_KEY);
  };

  const refreshUser = async () => {
    if (!token) return;
    const profile = await api.me();
    setUser(profile);
  };

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

