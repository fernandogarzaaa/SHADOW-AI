import React, { useEffect, useState } from 'react';
import { Modal, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { api, loadBaseUrl } from './src/api';
import { DesignConceptScreen, getRequestedConcept } from './src/concepts';
import { theme } from './src/theme';
import { AmbientBackground, Pill } from './src/ui';
import {
  ActionsScreen,
  ApprovalsScreen,
  AskScreen,
  AuditScreen,
  MemoryScreen,
  ModelsScreen,
  SettingsScreen,
} from './src/screens';

const Tab = createBottomTabNavigator();

const navTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    primary: theme.cyan,
    background: theme.bg,
    card: theme.glass,
    text: theme.txt,
    border: theme.stroke,
    notification: theme.violet,
  },
};

const TAB_GLYPHS: Record<string, string> = {
  Ask: '?',
  Memory: 'M',
  Actions: '>',
  Models: 'AI',
  Approvals: 'Y',
  Audit: '#',
};

function TabMark({ focused, label }: { focused: boolean; label: string }) {
  return (
    <View style={[s.tabMark, focused && s.tabMarkActive]}>
      <Text style={[s.tabMarkText, focused && s.tabMarkTextActive]}>{TAB_GLYPHS[label] || label.slice(0, 1)}</Text>
    </View>
  );
}

export default function App() {
  const requestedConcept = getRequestedConcept();
  if (requestedConcept) {
    return (
      <SafeAreaProvider>
        <StatusBar style={requestedConcept === '5' ? 'light' : 'dark'} />
        <SafeAreaView style={s.conceptApp} edges={['top', 'bottom']}>
          <DesignConceptScreen concept={requestedConcept} />
        </SafeAreaView>
      </SafeAreaProvider>
    );
  }

  return <MainApp />;
}

function MainApp() {
  const [status, setStatus] = useState<{ version?: string; paused?: boolean; online: boolean }>({ online: false });
  const [showSettings, setShowSettings] = useState(false);

  const refresh = async () => {
    try {
      const h = await api.health();
      setStatus({ version: h.version, paused: h.emergency_paused, online: true });
    } catch {
      setStatus((cur) => ({ ...cur, online: false }));
    }
  };

  useEffect(() => {
    loadBaseUrl().then(refresh);
    const id = setInterval(refresh, 8000);
    return () => clearInterval(id);
  }, []);

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <SafeAreaView style={s.app} edges={['top']}>
        <AmbientBackground />
        <View style={s.header}>
          <View style={s.brand}>
            <View style={s.glyph}>
              <View style={s.glyphCore} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.brandName}>Shadow</Text>
              <Text style={s.brandSub} numberOfLines={1}>
                {status.online ? `node ${status.version || 'ready'}` : 'offline'}
              </Text>
            </View>
          </View>
          <View style={s.headerRight}>
            <Pressable onPress={async () => { await api.emergencyPause(!status.paused).catch(() => {}); refresh(); }}>
              <Pill tone={status.paused ? 'bad' : undefined} text={status.paused ? 'paused' : 'pause'} />
            </Pressable>
            <Pressable onPress={() => setShowSettings(true)}>
              <Text style={s.settingsButton}>Settings</Text>
            </Pressable>
          </View>
        </View>

        <NavigationContainer theme={navTheme as any}>
          <Tab.Navigator
            screenOptions={({ route }) => ({
              headerShown: false,
              tabBarActiveTintColor: theme.txt,
              tabBarInactiveTintColor: theme.muted,
              tabBarStyle: s.tabBar,
              tabBarLabelStyle: s.tabLabel,
              tabBarItemStyle: s.tabItem,
              tabBarIcon: ({ focused }) => <TabMark focused={focused} label={route.name} />,
            })}>
            <Tab.Screen name="Ask" component={AskScreen} />
            <Tab.Screen name="Memory" component={MemoryScreen} />
            <Tab.Screen name="Actions" component={ActionsScreen} />
            <Tab.Screen name="Models" component={ModelsScreen} />
            <Tab.Screen name="Approvals" component={ApprovalsScreen} />
            <Tab.Screen name="Audit" component={AuditScreen} />
          </Tab.Navigator>
        </NavigationContainer>

        <Modal visible={showSettings} animationType="slide" onRequestClose={() => setShowSettings(false)}>
          <SafeAreaView style={s.app}>
            <AmbientBackground />
            <View style={s.header}>
              <Text style={s.brandName}>Settings</Text>
              <Pressable onPress={() => setShowSettings(false)}><Text style={s.settingsButton}>Done</Text></Pressable>
            </View>
            <SettingsScreen />
          </SafeAreaView>
        </Modal>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  app: { flex: 1, backgroundColor: theme.bg, overflow: 'hidden' },
  conceptApp: { flex: 1, overflow: 'hidden' },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 18,
    paddingVertical: 14,
    borderBottomColor: theme.stroke,
    borderBottomWidth: 1,
    backgroundColor: 'rgba(5, 7, 10, 0.72)',
  },
  brand: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 12, minWidth: 0 },
  glyph: {
    width: 38,
    height: 38,
    borderRadius: 15,
    backgroundColor: 'rgba(141, 133, 255, 0.26)',
    borderColor: theme.strokeStrong,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  glyphCore: { width: 16, height: 16, borderRadius: 8, backgroundColor: theme.cyan },
  brandName: { color: theme.txt, fontWeight: '800', fontSize: 18, letterSpacing: 0 },
  brandSub: { color: theme.faint, fontSize: 12, marginTop: 1 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 10, marginLeft: 12 },
  settingsButton: {
    color: theme.txt,
    fontSize: 12,
    fontWeight: '700',
    borderColor: theme.stroke,
    borderWidth: 1,
    borderRadius: 99,
    paddingHorizontal: 12,
    paddingVertical: 7,
    overflow: 'hidden',
    backgroundColor: 'rgba(255, 255, 255, 0.06)',
  },
  tabBar: {
    position: Platform.OS === 'web' ? 'relative' : 'absolute',
    backgroundColor: 'rgba(13, 18, 26, 0.86)',
    borderTopColor: theme.stroke,
    borderTopWidth: 1,
    minHeight: 76,
    paddingTop: 8,
    paddingBottom: 10,
  },
  tabItem: { paddingVertical: 4 },
  tabLabel: { fontSize: 11, fontWeight: '700', marginTop: 2 },
  tabMark: {
    width: 28,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(255, 255, 255, 0.04)',
    borderColor: theme.stroke,
    borderWidth: 1,
  },
  tabMarkActive: {
    backgroundColor: 'rgba(79, 216, 255, 0.18)',
    borderColor: 'rgba(79, 216, 255, 0.44)',
  },
  tabMarkText: { color: theme.faint, fontWeight: '800', fontSize: 11 },
  tabMarkTextActive: { color: theme.cyan },
});
