import React, { createContext, useContext, useEffect, useState } from 'react';
import { useColorScheme } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DARK_PALETTE, LIGHT_PALETTE, MeridianPalette } from '@/theme/colors';

export type ThemePreference = 'light' | 'dark' | 'system';

interface ThemeContextValue {
  preference: ThemePreference;
  palette: MeridianPalette;
  isDark: boolean;
  setThemePreference: (next: ThemePreference) => void;
  toggleTheme: () => void;
}

const STORAGE_KEY = 'meridian_theme_preference';

const ThemeContext = createContext<ThemeContextValue>({
  preference: 'system',
  palette: LIGHT_PALETTE,
  isDark: false,
  setThemePreference: () => {},
  toggleTheme: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const systemScheme = useColorScheme();
  const [preference, setPreference] = useState<ThemePreference>('system');

  useEffect(() => {
    AsyncStorage.getItem(STORAGE_KEY).then((saved) => {
      if (saved === 'light' || saved === 'dark' || saved === 'system') {
        setPreference(saved);
      }
    });
  }, []);

  const setThemePreference = (next: ThemePreference) => {
    setPreference(next);
    AsyncStorage.setItem(STORAGE_KEY, next).catch(() => {});
  };

  const resolvedScheme = preference === 'system' ? (systemScheme ?? 'light') : preference;
  const isDark = resolvedScheme === 'dark';
  const palette = isDark ? DARK_PALETTE : LIGHT_PALETTE;

  const toggleTheme = () => {
    setThemePreference(isDark ? 'light' : 'dark');
  };

  return (
    <ThemeContext.Provider value={{ preference, palette, isDark, setThemePreference, toggleTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

