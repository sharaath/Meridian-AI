import React, { useState } from 'react';
import { Linking, Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '@/contexts/ThemeContext';

interface CodeBlockProps {
  language: string;
  code: string;
}

const CODE_KEYWORDS = new Set([
  'import', 'from', 'export', 'default', 'const', 'let', 'var', 'function', 'return', 'async', 'await',
  'if', 'else', 'for', 'while', 'try', 'catch', 'finally', 'class', 'extends', 'def', 'None', 'True',
  'False', 'true', 'false', 'null', 'undefined', 'interface', 'type', 'SELECT', 'FROM', 'WHERE',
  'CREATE', 'TABLE', 'INSERT', 'INTO', 'VALUES', 'public', 'private', 'static', 'void', 'new',
]);

function renderHighlightedLine(line: string, keyPrefix: string) {
  const trimmed = line.trimStart();
  if (trimmed.startsWith('//') || trimmed.startsWith('#')) {
    return (
      <Text key={keyPrefix} style={{ color: '#94A3B8', fontStyle: 'italic' }}>
        {line}
      </Text>
    );
  }
  const tokens = line.split(/(\s+|[(){}[\].,:;'"`=+*/<>-]+)/);
  return (
    <Text key={keyPrefix} style={{ color: '#E2E8F0' }}>
      {tokens.map((tok, idx) => {
        if (!tok) return null;
        if (CODE_KEYWORDS.has(tok)) {
          return (
            <Text key={`${keyPrefix}-${idx}`} style={{ color: '#38BDF8', fontWeight: '600' }}>
              {tok}
            </Text>
          );
        }
        if (/^\d+(\.\d+)?$/.test(tok)) {
          return (
            <Text key={`${keyPrefix}-${idx}`} style={{ color: '#FBBF24' }}>
              {tok}
            </Text>
          );
        }
        if ((tok.startsWith('"') && tok.endsWith('"')) || (tok.startsWith("'") && tok.endsWith("'"))) {
          return (
            <Text key={`${keyPrefix}-${idx}`} style={{ color: '#34D399' }}>
              {tok}
            </Text>
          );
        }
        return tok;
      })}
    </Text>
  );
}

function CodeBlock({ language, code }: CodeBlockProps) {
  const { palette } = useTheme();
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await Clipboard.setStringAsync(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  const lines = code.split('\n');

  return (
    <View style={[styles.codeContainer, { backgroundColor: palette.codeBg, borderColor: palette.border }]}>
      <View style={[styles.codeHeader, { backgroundColor: palette.codeHeader }]}>
        <Text style={styles.codeLang}>{language || 'code'}</Text>
        <TouchableOpacity onPress={handleCopy} style={styles.copyCodeBtn}>
          <Ionicons name={copied ? 'checkmark' : 'copy-outline'} size={14} color="#CBD5E1" />
          <Text style={styles.copyCodeText}>{copied ? 'Copied' : 'Copy code'}</Text>
        </TouchableOpacity>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={styles.codeBody}>
          {lines.map((line, i) => (
            <Text key={i} selectable style={styles.codeText}>
              {renderHighlightedLine(line, `l-${i}`)}
            </Text>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

function renderInline(text: string, textColor: string, accentColor: string, codeBg: string): React.ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g);
  return parts.map((part, idx) => {
    if (!part) return null;
    if (part.startsWith('`') && part.endsWith('`') && part.length >= 2) {
      return (
        <Text
          key={idx}
          style={{
            fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
            fontSize: 13.5,
            backgroundColor: codeBg,
            color: accentColor,
          }}
        >
          {` ${part.slice(1, -1)} `}
        </Text>
      );
    }
    if (part.startsWith('**') && part.endsWith('**')) {
      return (
        <Text key={idx} style={{ fontWeight: '700', color: textColor }}>
          {part.slice(2, -2)}
        </Text>
      );
    }
    if (part.startsWith('*') && part.endsWith('*') && part.length > 2) {
      return (
        <Text key={idx} style={{ fontStyle: 'italic', color: textColor }}>
          {part.slice(1, -1)}
        </Text>
      );
    }
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      const [, label, url] = linkMatch;
      return (
        <Text
          key={idx}
          onPress={() => Linking.openURL(url).catch(() => {})}
          style={{ color: accentColor, textDecorationLine: 'underline', fontWeight: '500' }}
        >
          {label}
        </Text>
      );
    }
    return part;
  });
}

type Block =
  | { type: 'code'; language: string; content: string }
  | { type: 'table'; headers: string[]; rows: string[][] }
  | { type: 'text'; content: string };

function splitBlocks(markdown: string): Block[] {
  const lines = markdown.split('\n');
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Fenced code block
    if (line.trimStart().startsWith('```')) {
      const lang = line.trimStart().slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trimStart().startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: 'code', language: lang, content: codeLines.join('\n') });
      continue;
    }

    // Markdown table detection
    if (
      line.includes('|') &&
      i + 1 < lines.length &&
      /^\s*\|?\s*[-:]+[-|\s:]*$/.test(lines[i + 1])
    ) {
      const parseRow = (r: string) =>
        r
          .trim()
          .replace(/^\|/, '')
          .replace(/\|$/, '')
          .split('|')
          .map((c) => c.trim());

      const headers = parseRow(line);
      i += 2; // skip header and separator
      const rows: string[][] = [];
      while (i < lines.length && lines[i].includes('|') && lines[i].trim() !== '') {
        rows.push(parseRow(lines[i]));
        i++;
      }
      blocks.push({ type: 'table', headers, rows });
      continue;
    }

    const textLines: string[] = [];
    while (
      i < lines.length &&
      !lines[i].trimStart().startsWith('```') &&
      !(lines[i].includes('|') && i + 1 < lines.length && /^\s*\|?\s*[-:]+[-|\s:]*$/.test(lines[i + 1]))
    ) {
      textLines.push(lines[i]);
      i++;
    }
    if (textLines.length) {
      blocks.push({ type: 'text', content: textLines.join('\n') });
    }
  }

  return blocks;
}

export function MarkdownRenderer({ content, textColor }: { content: string; textColor?: string }) {
  const { palette } = useTheme();
  const fg = textColor || palette.text;
  const blocks = splitBlocks(content);

  return (
    <View style={{ gap: 8 }}>
      {blocks.map((block, bIdx) => {
        if (block.type === 'code') {
          return <CodeBlock key={bIdx} language={block.language} code={block.content} />;
        }

        if (block.type === 'table') {
          return (
            <ScrollView
              key={bIdx}
              horizontal
              showsHorizontalScrollIndicator
              style={[styles.tableWrapper, { borderColor: palette.border }]}
            >
              <View>
                <View style={[styles.tableRow, { backgroundColor: palette.surfaceElevated, borderBottomColor: palette.border }]}>
                  {block.headers.map((h, hIdx) => (
                    <Text key={hIdx} selectable style={[styles.tableCell, styles.tableHeaderText, { color: fg, borderRightColor: palette.border }]}>
                      {h}
                    </Text>
                  ))}
                </View>
                {block.rows.map((row, rIdx) => (
                  <View key={rIdx} style={[styles.tableRow, { borderBottomColor: palette.border }]}>
                    {block.headers.map((_, cIdx) => (
                      <Text key={cIdx} selectable style={[styles.tableCell, { color: fg, borderRightColor: palette.border }]}>
                        {renderInline(row[cIdx] || '', fg, palette.accent, palette.surfaceElevated)}
                      </Text>
                    ))}
                  </View>
                ))}
              </View>
            </ScrollView>
          );
        }

        const lines = block.content.split('\n');
        return (
          <View key={bIdx} style={{ gap: 4 }}>
            {lines.map((rawLine, lIdx) => {
              const trimmed = rawLine.trim();
              if (!trimmed) return <View key={lIdx} style={{ height: 4 }} />;

              if (trimmed.startsWith('### ')) {
                return (
                  <Text key={lIdx} selectable style={{ fontSize: 16, fontWeight: '700', color: fg, marginTop: 6 }}>
                    {renderInline(trimmed.slice(4), fg, palette.accent, palette.surfaceElevated)}
                  </Text>
                );
              }
              if (trimmed.startsWith('## ')) {
                return (
                  <Text key={lIdx} selectable style={{ fontSize: 18, fontWeight: '700', color: fg, marginTop: 8 }}>
                    {renderInline(trimmed.slice(3), fg, palette.accent, palette.surfaceElevated)}
                  </Text>
                );
              }
              if (trimmed.startsWith('# ')) {
                return (
                  <Text key={lIdx} selectable style={{ fontSize: 20, fontWeight: '800', color: fg, marginTop: 8 }}>
                    {renderInline(trimmed.slice(2), fg, palette.accent, palette.surfaceElevated)}
                  </Text>
                );
              }
              if (trimmed.startsWith('> ')) {
                return (
                  <View key={lIdx} style={[styles.blockquote, { borderLeftColor: palette.accent, backgroundColor: palette.surfaceElevated }]}>
                    <Text selectable style={{ fontSize: 15, lineHeight: 22, color: palette.textSecondary }}>
                      {renderInline(trimmed.slice(2), palette.textSecondary, palette.accent, palette.surface)}
                    </Text>
                  </View>
                );
              }
              if (/^[-*]\s+/.test(trimmed)) {
                return (
                  <View key={lIdx} style={styles.listItem}>
                    <Text style={{ color: palette.accent, fontWeight: '700', marginRight: 8 }}>•</Text>
                    <Text selectable style={{ flex: 1, fontSize: 15, lineHeight: 22, color: fg }}>
                      {renderInline(trimmed.replace(/^[-*]\s+/, ''), fg, palette.accent, palette.surfaceElevated)}
                    </Text>
                  </View>
                );
              }
              const numMatch = trimmed.match(/^(\d+\.)\s+(.*)$/);
              if (numMatch) {
                return (
                  <View key={lIdx} style={styles.listItem}>
                    <Text style={{ color: palette.accent, fontWeight: '600', marginRight: 8 }}>{numMatch[1]}</Text>
                    <Text selectable style={{ flex: 1, fontSize: 15, lineHeight: 22, color: fg }}>
                      {renderInline(numMatch[2], fg, palette.accent, palette.surfaceElevated)}
                    </Text>
                  </View>
                );
              }

              return (
                <Text key={lIdx} selectable style={{ fontSize: 15, lineHeight: 22, color: fg }}>
                  {renderInline(rawLine, fg, palette.accent, palette.surfaceElevated)}
                </Text>
              );
            })}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  codeContainer: {
    borderRadius: 12,
    borderWidth: 1,
    overflow: 'hidden',
    marginVertical: 4,
  },
  codeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  codeLang: {
    color: '#94A3B8',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  copyCodeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    backgroundColor: 'rgba(255,255,255,0.08)',
  },
  copyCodeText: {
    color: '#CBD5E1',
    fontSize: 12,
    fontWeight: '500',
  },
  codeBody: {
    padding: 12,
    minWidth: '100%',
  },
  codeText: {
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    fontSize: 13,
    lineHeight: 20,
    color: '#E2E8F0',
  },
  tableWrapper: {
    borderWidth: 1,
    borderRadius: 10,
    marginVertical: 4,
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
  },
  tableCell: {
    minWidth: 120,
    maxWidth: 240,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 13.5,
    borderRightWidth: 1,
  },
  tableHeaderText: {
    fontWeight: '700',
  },
  blockquote: {
    borderLeftWidth: 3,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 4,
  },
  listItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    paddingLeft: 4,
  },
});

