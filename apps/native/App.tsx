import React, { useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, Modal } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { theme } from './src/theme';
import { api, loadBaseUrl } from './src/api';
import {
  AskScreen, MemoryScreen, ActionsScreen, ModelsScreen,
  ApprovalsScreen, AuditScreen, SettingsScreen,
} from './src/screens';

const Tab = createBottomTabNavigator();

const navTheme = {
  ...DefaultTheme,
  dark: true,
  colors: {
    ...DefaultTheme.colors,
    primary: theme.accent,
    background: theme.bg,
    card: theme.panel,
    text: theme.txt,
    border: theme.line,
    notification: theme.accent,
  },
};

function Dot({ color }: { color: string }) {
  return <View style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: color }} />;
}

export default function App() {
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
        <View style={s.header}>
          <View style={s.brand}>
            <View style={s.glyph} />
            <View>
              <Text style={s.brandName}>Shadow</Text>
              <Text style={s.brandSub}>{status.online ? `node ${status.version || ''}` : 'offline — set node in settings'}</Text>
            </View>
          </View>
          <View style={s.headerRight}>
            <Pressable onPress={async () => { await api.emergencyPause(!status.paused).catch(() => {}); refresh(); }}>
              <Text style={[s.chip, status.paused && { color: theme.bad, borderColor: theme.bad }]}>
                {status.paused ? '⏸ paused' : 'pause'}
              </Text>
            </Pressable>
            <Pressable onPress={() => setShowSettings(true)}>
              <Text style={s.chip}>⚙</Text>
            </Pressable>
          </View>
        </View>

        <NavigationContainer theme={navTheme as any}>
          <Tab.Navigator
            screenOptions={({ route }) => ({
              headerShown: false,
              tabBarActiveTintColor: theme.txt,
              tabBarInactiveTintColor: theme.muted,
              tabBarStyle: { backgroundColor: theme.panel, borderTopColor: theme.line },
              tabBarLabelStyle: { fontSize: 11, fontWeight: '500' },
              tabBarIcon: ({ focused }) => <Dot color={focused ? theme.accent : theme.faint} />,
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
            <View style={s.header}>
              <Text style={s.brandName}>Settings</Text>
              <Pressable onPress={() => setShowSettings(false)}><Text style={s.chip}>Done</Text></Pressable>
            </View>
            <SettingsScreen />
          </SafeAreaView>
        </Modal>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  app: { flex: 1, backgroundColor: theme.bg },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 18, paddingVertical: 12, borderBottomColor: theme.line, borderBottomWidth: 1 },
  brand: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  glyph: { width: 26, height: 26, borderRadius: 8, backgroundColor: theme.accent },
  brandName: { color: theme.txt, fontWeight: '600', fontSize: 16 },
  brandSub: { color: theme.faint, fontSize: 11 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  chip: { color: theme.muted, fontSize: 12, borderColor: theme.line, borderWidth: 1, borderRadius: 8, paddingHorizontal: 11, paddingVertical: 6, overflow: 'hidden' },
});
