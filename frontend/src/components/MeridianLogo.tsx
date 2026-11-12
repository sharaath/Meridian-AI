import React from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle, Path, Rect } from 'react-native-svg';
import { useTheme } from '@/contexts/ThemeContext';

interface Props {
  size?: number;
  showText?: boolean;
}

export function MeridianLogo({ size = 32, showText = true }: Props) {
  const { palette } = useTheme();
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
      <Svg width={size} height={size} viewBox="0 0 40 40" fill="none">
        <Rect width="40" height="40" rx="11" fill={palette.accent} />
        <Path
          d="M20 7L23.4 16.6L33 20L23.4 23.4L20 33L16.6 23.4L7 20L16.6 16.6L20 7Z"
          fill="#FFFFFF"
        />
        <Circle cx="20" cy="20" r="3.2" fill={palette.accent} />
      </Svg>
      {showText && (
        <Text
          style={{
            fontSize: Math.round(size * 0.56),
            fontWeight: '700',
            letterSpacing: -0.4,
            color: palette.text,
          }}
        >
          Meridian
        </Text>
      )}
    </View>
  );
}

