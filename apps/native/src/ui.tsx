import React from 'react';
import {
  Platform,
  Pressable,
  ScrollView,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextStyle,
  View,
  ViewStyle,
} from 'react-native';
import { theme } from './theme';

export function AmbientBackground() {
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <View style={[styles.orb, styles.orbCyan]} />
      <View style={[styles.orb, styles.orbViolet]} />
      <View style={[styles.orb, styles.orbRose]} />
      <View style={styles.noiseVeil} />
    </View>
  );
}

export function Screen({ children }: { children: React.ReactNode }) {
  return (
    <View style={styles.screen}>
      <AmbientBackground />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled">
        {children}
      </ScrollView>
    </View>
  );
}

export function GlassCard({
  title,
  eyebrow,
  right,
  children,
  style,
}: {
  title?: string;
  eyebrow?: string;
  right?: React.ReactNode;
  children?: React.ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.card, style]}>
      <View pointerEvents="none" style={styles.glassHighlight} />
      {(title || eyebrow || right) ? (
        <View style={styles.cardHeader}>
          <View style={{ flex: 1 }}>
            {eyebrow ? <Text style={styles.eyebrow}>{eyebrow}</Text> : null}
            {title ? <Text style={styles.cardTitle}>{title}</Text> : null}
          </View>
          {right}
        </View>
      ) : null}
      {children}
    </View>
  );
}

export const Card = GlassCard;

export function Field(props: React.ComponentProps<typeof TextInput> & { label?: string }) {
  const { label, style, ...rest } = props;
  return (
    <View style={styles.fieldWrap}>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <TextInput
        placeholderTextColor={theme.faint}
        selectionColor={theme.cyan}
        style={[styles.input, style as StyleProp<TextStyle>]}
        {...rest}
      />
    </View>
  );
}

export function Button({
  title,
  onPress,
  kind = 'primary',
  disabled,
  wide,
}: {
  title: string;
  onPress?: () => void;
  kind?: 'primary' | 'ghost' | 'danger' | 'quiet';
  disabled?: boolean;
  wide?: boolean;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.btnBase,
        kind === 'primary' && styles.btnPrimary,
        kind === 'ghost' && styles.btnGhost,
        kind === 'danger' && styles.btnDanger,
        kind === 'quiet' && styles.btnQuiet,
        wide && { flex: 1 },
        pressed && styles.pressed,
        disabled && styles.disabled,
      ]}>
      <Text style={[styles.btnText, kind !== 'primary' && styles.btnTextMuted]} numberOfLines={1}>
        {title}
      </Text>
    </Pressable>
  );
}

export function Pill({ text, tone }: { text: string; tone?: 'ok' | 'warn' | 'bad' | 'accent' }) {
  const color =
    tone === 'ok' ? theme.ok :
    tone === 'warn' ? theme.warn :
    tone === 'bad' ? theme.bad :
    tone === 'accent' ? theme.cyan :
    theme.muted;
  return (
    <Text style={[styles.pill, { color, borderColor: color + '55' }]} numberOfLines={1}>
      {text}
    </Text>
  );
}

export function Metric({ label, value, tone = 'accent' }: { label: string; value: string; tone?: 'accent' | 'ok' | 'warn' }) {
  const color = tone === 'ok' ? theme.ok : tone === 'warn' ? theme.warn : theme.cyan;
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, { color }]} numberOfLines={1}>{value}</Text>
      <Text style={styles.metricLabel} numberOfLines={1}>{label}</Text>
    </View>
  );
}

export function GlassListItem({
  title,
  subtitle,
  right,
}: {
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}) {
  return (
    <View style={styles.listItem}>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={styles.itemTitle} numberOfLines={1}>{title}</Text>
        {subtitle ? <Text style={styles.itemDesc} numberOfLines={2}>{subtitle}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export function LoadingBar({ active }: { active: boolean }) {
  return (
    <View style={[styles.loadingTrack, !active && { opacity: 0 }]}>
      <View style={styles.loadingFill} />
    </View>
  );
}

export function SegmentedControl({
  items,
  value,
  onChange,
}: {
  items: string[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.segment}>
      {items.map((item) => {
        const active = item === value;
        return (
          <Pressable key={item} onPress={() => onChange(item)} style={[styles.segmentItem, active && styles.segmentActive]}>
            <Text style={[styles.segmentText, active && styles.segmentTextActive]} numberOfLines={1}>{item}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: theme.bg, overflow: 'hidden' },
  scroll: { flex: 1, overflow: 'hidden' },
  scrollContent: { padding: 18, paddingBottom: 110 },
  orb: { position: 'absolute', width: 260, height: 260, borderRadius: 130, opacity: 0.22 },
  orbCyan: { backgroundColor: theme.cyan, top: -90, right: -80 },
  orbViolet: { backgroundColor: theme.violet, top: 190, left: -130 },
  orbRose: { backgroundColor: theme.rose, bottom: 40, right: -150, opacity: 0.14 },
  noiseVeil: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, backgroundColor: 'rgba(5, 7, 10, 0.58)' },
  card: {
    backgroundColor: theme.glass,
    borderColor: theme.stroke,
    borderWidth: 1,
    borderRadius: theme.radius,
    padding: 18,
    marginBottom: theme.gap,
    overflow: 'hidden',
    ...Platform.select({
      ios: { shadowColor: '#000', shadowOpacity: 0.28, shadowRadius: 24, shadowOffset: { width: 0, height: 18 } },
      android: { elevation: 7 },
      web: { boxShadow: '0 22px 60px rgba(0,0,0,0.32)' } as any,
    }),
  },
  glassHighlight: {
    position: 'absolute',
    left: 1,
    right: 1,
    top: 1,
    height: 56,
    borderTopLeftRadius: theme.radius,
    borderTopRightRadius: theme.radius,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
  },
  cardHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: 16 },
  eyebrow: { color: theme.cyan, fontSize: 11, fontWeight: '700', letterSpacing: 0, textTransform: 'uppercase', marginBottom: 4 },
  cardTitle: { color: theme.txt, fontSize: 20, fontWeight: '700', letterSpacing: 0 },
  label: { color: theme.muted, fontSize: 12, marginBottom: 7, fontWeight: '600' },
  fieldWrap: { marginBottom: 12 },
  input: {
    backgroundColor: 'rgba(255, 255, 255, 0.07)',
    borderColor: theme.stroke,
    borderWidth: 1,
    borderRadius: theme.radiusSm,
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: theme.txt,
    minHeight: 46,
  },
  btnBase: {
    minHeight: 44,
    paddingVertical: 11,
    paddingHorizontal: 16,
    borderRadius: theme.radiusSm,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: theme.stroke,
  },
  btnPrimary: { backgroundColor: theme.violet, borderColor: 'rgba(255, 255, 255, 0.24)' },
  btnGhost: { backgroundColor: 'rgba(255, 255, 255, 0.06)' },
  btnDanger: { backgroundColor: 'rgba(255, 111, 145, 0.10)', borderColor: 'rgba(255, 111, 145, 0.36)' },
  btnQuiet: { backgroundColor: 'transparent', borderColor: 'transparent' },
  pressed: { transform: [{ scale: 0.985 }], opacity: 0.9 },
  disabled: { opacity: 0.5 },
  btnText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  btnTextMuted: { color: theme.muted },
  pill: {
    fontSize: 11,
    borderWidth: 1,
    borderRadius: 99,
    paddingHorizontal: 9,
    paddingVertical: 4,
    overflow: 'hidden',
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    maxWidth: 190,
  },
  metric: {
    flex: 1,
    minWidth: 92,
    borderRadius: theme.radiusSm,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderColor: theme.stroke,
    borderWidth: 1,
    padding: 12,
  },
  metricValue: { fontSize: 18, fontWeight: '800', letterSpacing: 0 },
  metricLabel: { color: theme.faint, fontSize: 11, marginTop: 2 },
  segment: {
    flexDirection: 'row',
    padding: 4,
    borderRadius: theme.radiusSm,
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
    borderWidth: 1,
    borderColor: theme.stroke,
    gap: 4,
  },
  segmentItem: { flex: 1, minHeight: 36, alignItems: 'center', justifyContent: 'center', borderRadius: 11, paddingHorizontal: 8 },
  segmentActive: { backgroundColor: 'rgba(141, 133, 255, 0.26)', borderWidth: 1, borderColor: 'rgba(141, 133, 255, 0.36)' },
  segmentText: { color: theme.muted, fontSize: 12, fontWeight: '700' },
  segmentTextActive: { color: theme.txt },
  answer: {
    color: theme.txt,
    backgroundColor: 'rgba(255, 255, 255, 0.07)',
    borderColor: 'rgba(79, 216, 255, 0.45)',
    borderWidth: 1,
    borderRadius: theme.radiusSm,
    padding: 14,
    marginTop: 12,
    lineHeight: 20,
  },
  item: {
    borderColor: theme.stroke,
    borderWidth: 1,
    borderRadius: theme.radiusSm,
    padding: 13,
    marginBottom: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.055)',
  },
  listItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderColor: theme.stroke,
    borderWidth: 1,
    borderRadius: theme.radiusSm,
    padding: 13,
    marginBottom: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.055)',
  },
  itemTitle: { color: theme.txt, fontWeight: '700', fontSize: 14 },
  itemDesc: { color: theme.muted, fontSize: 13, marginTop: 4, lineHeight: 18 },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  empty: { color: theme.faint, fontSize: 13, textAlign: 'center', paddingVertical: 22 },
  meta: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  loadingTrack: {
    height: 3,
    overflow: 'hidden',
    borderRadius: 99,
    backgroundColor: 'rgba(255, 255, 255, 0.08)',
    marginTop: 14,
  },
  loadingFill: {
    width: '58%',
    height: 3,
    borderRadius: 99,
    backgroundColor: theme.cyan,
  },
});
