import React from 'react';
import { View, Text, TextInput, Pressable, StyleSheet, ViewStyle } from 'react-native';
import { theme } from './theme';

export function Card({ title, hint, children }: { title?: string; hint?: string; children?: React.ReactNode }) {
  return (
    <View style={styles.card}>
      {title ? <Text style={styles.cardTitle}>{title}</Text> : null}
      {hint ? <Text style={styles.cardHint}>{hint}</Text> : null}
      {children}
    </View>
  );
}

export function Field(props: React.ComponentProps<typeof TextInput> & { label?: string }) {
  const { label, style, ...rest } = props;
  return (
    <View>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput placeholderTextColor={theme.faint} style={[styles.input, style as ViewStyle]} {...rest} />
    </View>
  );
}

export function Button({ title, onPress, kind = 'primary', disabled }: { title: string; onPress?: () => void; kind?: 'primary' | 'ghost' | 'danger'; disabled?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btnBase,
        kind === 'primary' && styles.btnPrimary,
        kind === 'ghost' && styles.btnGhost,
        kind === 'danger' && styles.btnDanger,
        pressed && { opacity: 0.85 },
        disabled && { opacity: 0.5 },
      ]}>
      <Text style={[styles.btnText, kind !== 'primary' && { color: kind === 'danger' ? theme.bad : theme.muted }]}>{title}</Text>
    </Pressable>
  );
}

export function Pill({ text, tone }: { text: string; tone?: 'ok' | 'warn' | 'bad' }) {
  const color = tone === 'ok' ? theme.ok : tone === 'warn' ? theme.warn : tone === 'bad' ? theme.bad : theme.muted;
  return <Text style={[styles.pill, { color }]}>{text}</Text>;
}

export const styles = StyleSheet.create({
  card: { backgroundColor: theme.panel, borderColor: theme.line, borderWidth: 1, borderRadius: theme.radius, padding: 18, marginBottom: theme.gap },
  cardTitle: { color: theme.txt, fontSize: 15, fontWeight: '600', marginBottom: 2 },
  cardHint: { color: theme.faint, fontSize: 12.5, marginBottom: 12 },
  label: { color: theme.muted, fontSize: 12, marginBottom: 6, fontWeight: '500' },
  input: { backgroundColor: theme.panel2, borderColor: theme.line, borderWidth: 1, borderRadius: 10, paddingHorizontal: 13, paddingVertical: 11, color: theme.txt, marginBottom: 12 },
  btnBase: { paddingVertical: 11, paddingHorizontal: 16, borderRadius: 10, alignItems: 'center' },
  btnPrimary: { backgroundColor: theme.accent },
  btnGhost: { borderWidth: 1, borderColor: theme.line },
  btnDanger: { borderWidth: 1, borderColor: 'rgba(240,100,100,0.35)' },
  btnText: { color: '#fff', fontWeight: '600' },
  pill: { fontSize: 11, color: theme.muted, borderColor: theme.line, borderWidth: 1, borderRadius: 99, paddingHorizontal: 9, paddingVertical: 3, overflow: 'hidden' },
  answer: { color: theme.txt, backgroundColor: theme.panel2, borderColor: theme.accent, borderLeftWidth: 2, borderWidth: 1, borderRadius: 10, padding: 14, marginTop: 6 },
  item: { borderColor: theme.line, borderWidth: 1, borderRadius: 11, padding: 13, marginBottom: 10, backgroundColor: theme.panel2 },
  itemTitle: { color: theme.txt, fontWeight: '500' },
  itemDesc: { color: theme.muted, fontSize: 13, marginTop: 2 },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  empty: { color: theme.faint, fontSize: 13, textAlign: 'center', paddingVertical: 22 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
});
