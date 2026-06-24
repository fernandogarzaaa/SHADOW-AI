import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView, Pressable, StyleSheet, SafeAreaView } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { theme } from './src/theme';
import { api, loadBaseUrl } from './src/api';
import { AskScreen, MemoryScreen, ActionsScreen, ModelsScreen, ApprovalsScreen, AuditScreen, SettingsScreen } from './src/screens';
import { registerPWA } from './src/pwa';

const TABS = [
  { key: 'ask', label: 'Ask', screen: AskScreen },
  { key: 'memory', label: 'Memory', screen: MemoryScreen },
  { key: 'actions', label: 'Actions', screen: ActionsScreen },
  { key: 'models', label: 'Models', screen: ModelsScreen },
  { key: 'approvals', label: 'Approvals', screen: ApprovalsScreen },
  { key: 'audit', label: 'Audit', screen: AuditScreen },
  { key: 'settings', label: 'Settings', screen: SettingsScreen },
];

export default function App() {
  const [tab, setTab] = useState('ask');
  const [status, setStatus] = useState<{ version?: string; paused?: boolean; online: boolean }>({ online: false });

  const refresh = async () => {
    try {
      const h = await api.health();
      setStatus({ version: h.version, paused: h.emergency_paused, online: true });
    } catch {
      setStatus((cur) => ({ ...cur, online: false }));
    }
  };

  useEffect(() => {
    registerPWA();
    loadBaseUrl().then(refresh);
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, []);

  const Screen = TABS.find((t) => t.key === tab)!.screen;

  return (
    <SafeAreaView style={s.app}>
      <StatusBar style="light" />
      <View style={s.header}>
        <View style={s.brand}>
          <View style={s.glyph} />
          <View>
            <Text style={s.brandName}>Shadow</Text>
            <Text style={s.brandSub}>{status.online ? `node ${status.version || ''}` : 'offline'}</Text>
          </View>
        </View>
        <Pressable onPress={async () => { await api.emergencyPause(!status.paused).catch(() => {}); refresh(); }}>
          <Text style={[s.pause, status.paused && { color: theme.bad, borderColor: theme.bad }]}>
            {status.paused ? '⏸ paused' : 'pause'}
          </Text>
        </Pressable>
      </View>

      <ScrollView style={s.body} contentContainerStyle={{ padding: 16, maxWidth: 760, width: '100%', alignSelf: 'center' }}>
        <Screen />
      </ScrollView>

      <View style={s.tabbar}>
        {TABS.map((t) => (
          <Pressable key={t.key} onPress={() => setTab(t.key)} style={s.tab}>
            <Text style={[s.tabLabel, tab === t.key && { color: theme.txt }]}>{t.label}</Text>
            {tab === t.key ? <View style={s.tabDot} /> : null}
          </Pressable>
        ))}
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  app: { flex: 1, backgroundColor: theme.bg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 18, paddingVertical: 14, borderBottomColor: theme.line, borderBottomWidth: 1 },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  glyph: { width: 26, height: 26, borderRadius: 8, backgroundColor: theme.accent },
  brandName: { color: theme.txt, fontWeight: '600', fontSize: 16 },
  brandSub: { color: theme.faint, fontSize: 11 },
  pause: { color: theme.muted, fontSize: 12, borderColor: theme.line, borderWidth: 1, borderRadius: 8, paddingHorizontal: 11, paddingVertical: 6, overflow: 'hidden' },
  body: { flex: 1 },
  tabbar: { flexDirection: 'row', borderTopColor: theme.line, borderTopWidth: 1, backgroundColor: theme.panel },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 11, gap: 4 },
  tabLabel: { color: theme.muted, fontSize: 12, fontWeight: '500' },
  tabDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: theme.accent },
});
