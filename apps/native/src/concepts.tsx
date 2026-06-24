import React from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

export type ConceptId = '3' | '4' | '5';

export function getRequestedConcept(): ConceptId | null {
  if (Platform.OS !== 'web') return null;
  const search = (globalThis as any).location?.search || '';
  const concept = new URLSearchParams(search).get('concept');
  return concept === '3' || concept === '4' || concept === '5' ? concept : null;
}

export function DesignConceptScreen({ concept }: { concept: ConceptId }) {
  if (concept === '3') return <TamaguiBentoConcept />;
  if (concept === '4') return <GluestackUtilityConcept />;
  return <CraftEditorialConcept />;
}

function PhoneShell({ children, background }: { children: React.ReactNode; background: string }) {
  return (
    <View style={[conceptStyles.shell, { backgroundColor: background }]}>
      <ScrollView contentContainerStyle={conceptStyles.scroll} showsVerticalScrollIndicator={false}>
        {children}
      </ScrollView>
    </View>
  );
}

function Tag({ children, tone = 'neutral' }: { children: React.ReactNode; tone?: 'neutral' | 'good' | 'warn' | 'dark' }) {
  return (
    <Text
      style={[
        conceptStyles.tag,
        tone === 'good' && conceptStyles.tagGood,
        tone === 'warn' && conceptStyles.tagWarn,
        tone === 'dark' && conceptStyles.tagDark,
      ]}
      numberOfLines={1}>
      {children}
    </Text>
  );
}

function ApprovalStrip({ dark }: { dark?: boolean }) {
  return (
    <View style={[conceptStyles.approvalStrip, dark && conceptStyles.approvalStripDark]}>
      <View>
        <Text style={[conceptStyles.approvalTitle, dark && conceptStyles.darkText]}>Client approval</Text>
        <Text style={[conceptStyles.approvalSub, dark && conceptStyles.darkMuted]}>Three visual routes prepared before final build</Text>
      </View>
      <Tag tone={dark ? 'dark' : 'good'}>review</Tag>
    </View>
  );
}

function TamaguiBentoConcept() {
  return (
    <PhoneShell background="#eef4f0">
      <View style={bento.hero}>
        <View style={bento.brandRow}>
          <View style={bento.logo}>
            <Text style={bento.logoText}>S</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={bento.kicker}>Option 3</Text>
            <Text style={bento.title}>Shadow Brief</Text>
          </View>
          <Tag tone="good">paired</Tag>
        </View>
        <Text style={bento.headline}>A calmer bento workspace for private memory recall.</Text>
        <View style={bento.actions}>
          <Pressable style={bento.primaryButton}>
            <Text style={bento.primaryText}>Run demo</Text>
          </Pressable>
          <Pressable style={bento.secondaryButton}>
            <Text style={bento.secondaryText}>Ask</Text>
          </Pressable>
        </View>
      </View>

      <View style={bento.grid}>
        <View style={[bento.tile, bento.tileTall]}>
          <Text style={bento.tileLabel}>PRIVATE ANSWER</Text>
          <Text style={bento.answer}>Aurora ships in March. Dana owns the launch brief and source note.</Text>
          <View style={bento.sourceCard}>
            <Text style={bento.sourceTitle}>Recruiter demo note</Text>
            <Text style={bento.sourceText}>Project Aurora ships in March; lead is Dana.</Text>
          </View>
        </View>
        <View style={[bento.tile, bento.metricTile]}>
          <Text style={bento.metric}>80%</Text>
          <Text style={bento.metricLabel}>token savings</Text>
        </View>
        <View style={[bento.tile, bento.metricTile, { backgroundColor: '#182723' }]}>
          <Text style={[bento.metric, { color: '#d9ff72' }]}>local</Text>
          <Text style={[bento.metricLabel, { color: '#b5c4bd' }]}>route</Text>
        </View>
      </View>

      <View style={bento.panel}>
        <View style={bento.timelineItem}>
          <View style={bento.dot} />
          <View>
            <Text style={bento.timelineTitle}>Memory sealed</Text>
            <Text style={bento.timelineText}>Encrypted local store updated from mobile.</Text>
          </View>
        </View>
        <View style={bento.timelineItem}>
          <View style={[bento.dot, { backgroundColor: '#e15a40' }]} />
          <View>
            <Text style={bento.timelineTitle}>Approval required</Text>
            <Text style={bento.timelineText}>Actions wait for explicit review before running.</Text>
          </View>
        </View>
      </View>
      <ApprovalStrip />
    </PhoneShell>
  );
}

function GluestackUtilityConcept() {
  return (
    <PhoneShell background="#f7f8fb">
      <View style={utility.header}>
        <View>
          <Text style={utility.kicker}>Option 4</Text>
          <Text style={utility.title}>Shadow Control</Text>
        </View>
        <Tag tone="good">secure</Tag>
      </View>

      <View style={utility.card}>
        <Text style={utility.sectionTitle}>Private Memory Brief</Text>
        <Text style={utility.prompt}>When does Aurora ship and who leads it?</Text>
        <View style={utility.statusRow}>
          <View style={utility.statusPill}>
            <Text style={utility.statusText}>signed request</Text>
          </View>
          <View style={[utility.statusPill, { backgroundColor: '#ecfdf5', borderColor: '#b7ead2' }]}>
            <Text style={[utility.statusText, { color: '#047857' }]}>audit ready</Text>
          </View>
        </View>
        <Pressable style={utility.button}>
          <Text style={utility.buttonText}>Generate brief</Text>
        </Pressable>
      </View>

      <View style={utility.metrics}>
        <View style={utility.metricBox}>
          <Text style={utility.metricValue}>3</Text>
          <Text style={utility.metricLabel}>sources</Text>
        </View>
        <View style={utility.metricBox}>
          <Text style={utility.metricValue}>local</Text>
          <Text style={utility.metricLabel}>routing</Text>
        </View>
        <View style={utility.metricBox}>
          <Text style={utility.metricValue}>0</Text>
          <Text style={utility.metricLabel}>pending</Text>
        </View>
      </View>

      <View style={utility.table}>
        {[
          ['memory.ingest', 'allowed', '10:41'],
          ['agent.ask', 'answered', '10:42'],
          ['nonce.replay', 'blocked', '10:42'],
        ].map(([event, state, time]) => (
          <View key={event} style={utility.tableRow}>
            <Text style={utility.eventName}>{event}</Text>
            <Text style={[utility.eventState, state === 'blocked' && { color: '#dc2626' }]}>{state}</Text>
            <Text style={utility.eventTime}>{time}</Text>
          </View>
        ))}
      </View>

      <ApprovalStrip />
    </PhoneShell>
  );
}

function CraftEditorialConcept() {
  return (
    <PhoneShell background="#101114">
      <View style={editorial.masthead}>
        <Text style={editorial.issue}>Option 5 / Field Note</Text>
        <Text style={editorial.title}>Shadow for private recall</Text>
        <Text style={editorial.deck}>A story-led mobile sample where memory, consent, and auditability feel human instead of administrative.</Text>
      </View>

      <View style={editorial.featureImage}>
        <View style={editorial.featureBlockOne} />
        <View style={editorial.featureBlockTwo} />
        <View style={editorial.featureBlockThree} />
        <Text style={editorial.featureText}>AURORA</Text>
      </View>

      <View style={editorial.storyCard}>
        <Text style={editorial.storyEyebrow}>Brief generated from sealed memory</Text>
        <Text style={editorial.storyAnswer}>Aurora ships in March. Dana is the launch owner. The answer came from one local source and an auditable signed request.</Text>
        <View style={editorial.rule} />
        <View style={editorial.byline}>
          <View>
            <Text style={editorial.bylineLabel}>Route</Text>
            <Text style={editorial.bylineValue}>local first</Text>
          </View>
          <View>
            <Text style={editorial.bylineLabel}>Approval</Text>
            <Text style={editorial.bylineValue}>required</Text>
          </View>
        </View>
      </View>

      <View style={editorial.cards}>
        <View style={editorial.miniCard}>
          <Text style={editorial.miniNumber}>01</Text>
          <Text style={editorial.miniText}>Pair device</Text>
        </View>
        <View style={editorial.miniCard}>
          <Text style={editorial.miniNumber}>02</Text>
          <Text style={editorial.miniText}>Seal memory</Text>
        </View>
        <View style={editorial.miniCard}>
          <Text style={editorial.miniNumber}>03</Text>
          <Text style={editorial.miniText}>Review action</Text>
        </View>
      </View>

      <ApprovalStrip dark />
    </PhoneShell>
  );
}

const conceptStyles = StyleSheet.create({
  shell: { flex: 1 },
  scroll: { padding: 18, paddingBottom: 18, minHeight: 844 },
  tag: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#d8dee7',
    color: '#526070',
    backgroundColor: '#ffffff',
    paddingHorizontal: 10,
    paddingVertical: 5,
    overflow: 'hidden',
    fontSize: 11,
    fontWeight: '800',
    textTransform: 'uppercase',
  },
  tagGood: { color: '#047857', borderColor: '#9de5c3', backgroundColor: '#ecfdf5' },
  tagWarn: { color: '#9a3412', borderColor: '#fed7aa', backgroundColor: '#fff7ed' },
  tagDark: { color: '#f5f1e8', borderColor: '#474036', backgroundColor: '#27231d' },
  approvalStrip: {
    marginTop: 16,
    borderRadius: 18,
    padding: 14,
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: '#dfe6ed',
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 12,
  },
  approvalStripDark: { backgroundColor: '#18191d', borderColor: '#303139' },
  approvalTitle: { color: '#15202b', fontSize: 14, fontWeight: '800' },
  approvalSub: { color: '#657184', fontSize: 12, marginTop: 3, lineHeight: 16 },
  darkText: { color: '#f7f0e6' },
  darkMuted: { color: '#a49a8e' },
});

const bento = StyleSheet.create({
  hero: {
    borderRadius: 26,
    padding: 18,
    backgroundColor: '#fbfff9',
    borderWidth: 1,
    borderColor: '#dce9de',
    marginBottom: 14,
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 14 },
  logo: { width: 40, height: 40, borderRadius: 15, backgroundColor: '#19221f', alignItems: 'center', justifyContent: 'center' },
  logoText: { color: '#d9ff72', fontSize: 18, fontWeight: '900' },
  kicker: { color: '#5f766d', fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  title: { color: '#16201c', fontSize: 21, fontWeight: '900', marginTop: 2 },
  headline: { color: '#16201c', fontSize: 25, lineHeight: 30, fontWeight: '900' },
  actions: { flexDirection: 'row', gap: 10, marginTop: 15 },
  primaryButton: { flex: 1, backgroundColor: '#e15a40', borderRadius: 16, minHeight: 44, alignItems: 'center', justifyContent: 'center' },
  primaryText: { color: '#fff', fontWeight: '900', fontSize: 14 },
  secondaryButton: { width: 76, borderRadius: 16, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#ccd9cf' },
  secondaryText: { color: '#16201c', fontWeight: '900', fontSize: 14 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile: { borderRadius: 22, padding: 14, backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#dce5dc' },
  tileTall: { width: '100%', minHeight: 170 },
  tileLabel: { color: '#6d7a73', fontSize: 11, fontWeight: '900' },
  answer: { color: '#14211b', fontSize: 17, lineHeight: 24, fontWeight: '800', marginTop: 10 },
  sourceCard: { marginTop: 12, borderRadius: 18, padding: 12, backgroundColor: '#edf7ee' },
  sourceTitle: { color: '#17251f', fontSize: 13, fontWeight: '900' },
  sourceText: { color: '#60736a', fontSize: 12, marginTop: 5, lineHeight: 17 },
  metricTile: { flex: 1, minHeight: 88 },
  metric: { color: '#e15a40', fontSize: 25, fontWeight: '900' },
  metricLabel: { color: '#60736a', fontSize: 12, marginTop: 4, fontWeight: '700' },
  panel: { marginTop: 12, borderRadius: 22, padding: 13, backgroundColor: '#dcefe4', gap: 11 },
  timelineItem: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  dot: { width: 12, height: 12, borderRadius: 6, backgroundColor: '#16352a', marginTop: 4 },
  timelineTitle: { color: '#16201c', fontSize: 14, fontWeight: '900' },
  timelineText: { color: '#60736a', fontSize: 12, marginTop: 2, lineHeight: 16 },
});

const utility = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 },
  kicker: { color: '#52606f', fontSize: 12, fontWeight: '800', textTransform: 'uppercase' },
  title: { color: '#101828', fontSize: 30, fontWeight: '900', marginTop: 4 },
  card: { backgroundColor: '#ffffff', borderRadius: 14, borderWidth: 1, borderColor: '#e5e7eb', padding: 16 },
  sectionTitle: { color: '#111827', fontSize: 18, fontWeight: '900' },
  prompt: { marginTop: 14, borderRadius: 12, borderWidth: 1, borderColor: '#d1d5db', backgroundColor: '#f9fafb', color: '#111827', padding: 14, fontSize: 14, lineHeight: 20 },
  statusRow: { flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' },
  statusPill: { borderRadius: 999, backgroundColor: '#eff6ff', borderWidth: 1, borderColor: '#bfdbfe', paddingHorizontal: 10, paddingVertical: 6 },
  statusText: { color: '#1d4ed8', fontSize: 11, fontWeight: '900', textTransform: 'uppercase' },
  button: { marginTop: 16, minHeight: 48, borderRadius: 12, backgroundColor: '#2563eb', alignItems: 'center', justifyContent: 'center' },
  buttonText: { color: '#ffffff', fontSize: 14, fontWeight: '900' },
  metrics: { flexDirection: 'row', gap: 10, marginTop: 12 },
  metricBox: { flex: 1, borderRadius: 12, backgroundColor: '#ffffff', borderWidth: 1, borderColor: '#e5e7eb', padding: 12 },
  metricValue: { color: '#111827', fontSize: 18, fontWeight: '900' },
  metricLabel: { color: '#667085', fontSize: 11, marginTop: 4, fontWeight: '700' },
  table: { marginTop: 12, backgroundColor: '#ffffff', borderRadius: 14, borderWidth: 1, borderColor: '#e5e7eb', overflow: 'hidden' },
  tableRow: { minHeight: 48, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#eef0f3', gap: 8 },
  eventName: { flex: 1, color: '#111827', fontSize: 13, fontWeight: '800' },
  eventState: { width: 72, color: '#047857', fontSize: 12, fontWeight: '900' },
  eventTime: { color: '#667085', fontSize: 12, fontWeight: '700' },
});

const editorial = StyleSheet.create({
  masthead: { paddingTop: 4, marginBottom: 18 },
  issue: { color: '#d9a15f', fontSize: 12, fontWeight: '900', textTransform: 'uppercase' },
  title: { color: '#f7f0e6', fontSize: 31, lineHeight: 35, fontWeight: '900', marginTop: 8 },
  deck: { color: '#a49a8e', fontSize: 14, lineHeight: 20, marginTop: 9 },
  featureImage: { height: 148, borderRadius: 4, overflow: 'hidden', backgroundColor: '#201d19', marginBottom: 12, position: 'relative' },
  featureBlockOne: { position: 'absolute', left: 0, top: 0, bottom: 0, width: '42%', backgroundColor: '#d9a15f' },
  featureBlockTwo: { position: 'absolute', right: 0, top: 0, height: '55%', width: '58%', backgroundColor: '#3c5542' },
  featureBlockThree: { position: 'absolute', right: 0, bottom: 0, height: '45%', width: '58%', backgroundColor: '#b74937' },
  featureText: { position: 'absolute', left: 14, bottom: 10, color: '#101114', fontSize: 28, fontWeight: '900' },
  storyCard: { backgroundColor: '#f7f0e6', borderRadius: 4, padding: 15 },
  storyEyebrow: { color: '#8a4b36', fontSize: 11, fontWeight: '900', textTransform: 'uppercase' },
  storyAnswer: { color: '#171717', fontSize: 16, lineHeight: 23, fontWeight: '800', marginTop: 8 },
  rule: { height: 1, backgroundColor: '#d7cabb', marginVertical: 12 },
  byline: { flexDirection: 'row', justifyContent: 'space-between' },
  bylineLabel: { color: '#76695d', fontSize: 11, fontWeight: '900', textTransform: 'uppercase' },
  bylineValue: { color: '#171717', fontSize: 14, fontWeight: '900', marginTop: 4 },
  cards: { flexDirection: 'row', gap: 10, marginTop: 12 },
  miniCard: { flex: 1, minHeight: 74, borderRadius: 4, borderWidth: 1, borderColor: '#303139', padding: 11, justifyContent: 'space-between' },
  miniNumber: { color: '#d9a15f', fontSize: 12, fontWeight: '900' },
  miniText: { color: '#f7f0e6', fontSize: 12, lineHeight: 15, fontWeight: '800' },
});
