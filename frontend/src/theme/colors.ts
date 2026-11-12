export interface MeridianPalette {
  mode: 'light' | 'dark';
  bg: string;
  surface: string;
  surfaceElevated: string;
  sidebar: string;
  border: string;
  borderStrong: string;
  text: string;
  textSecondary: string;
  textMuted: string;
  accent: string;
  accentSoft: string;
  accentText: string;
  userBubble: string;
  userBubbleText: string;
  assistantBubble: string;
  codeBg: string;
  codeHeader: string;
  danger: string;
  dangerSoft: string;
  success: string;
  warning: string;
}

export const LIGHT_PALETTE: MeridianPalette = {
  mode: 'light',
  bg: '#FAF9F6',
  surface: '#FFFFFF',
  surfaceElevated: '#F3F1EC',
  sidebar: '#F4F2ED',
  border: '#E5E2DA',
  borderStrong: '#D0CBC0',
  text: '#18181B',
  textSecondary: '#4B5563',
  textMuted: '#71717A',
  accent: '#0D9488',
  accentSoft: '#CCFBF1',
  accentText: '#FFFFFF',
  userBubble: '#0F766E',
  userBubbleText: '#FFFFFF',
  assistantBubble: '#FFFFFF',
  codeBg: '#1E293B',
  codeHeader: '#0F172A',
  danger: '#DC2626',
  dangerSoft: '#FEE2E2',
  success: '#059669',
  warning: '#D97706',
};

export const DARK_PALETTE: MeridianPalette = {
  mode: 'dark',
  bg: '#0D1017',
  surface: '#151A23',
  surfaceElevated: '#1C2330',
  sidebar: '#11151E',
  border: '#242C3D',
  borderStrong: '#344058',
  text: '#F3F4F6',
  textSecondary: '#CBD5E1',
  textMuted: '#94A3B8',
  accent: '#14B8A6',
  accentSoft: '#134E4A',
  accentText: '#042F2E',
  userBubble: '#115E59',
  userBubbleText: '#F0FDFA',
  assistantBubble: '#151A23',
  codeBg: '#090C12',
  codeHeader: '#111622',
  danger: '#F87171',
  dangerSoft: '#450A0A',
  success: '#34D399',
  warning: '#FBBF24',
};

