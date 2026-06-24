import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Text, View } from 'react-native';
import { api, getBaseUrl, isPaired, pairDevice, setBaseUrl, unpair } from './api';
import { theme } from './theme';
import { Button, Field, GlassCard, Metric, Pill, Screen, SegmentedControl, styles } from './ui';

const PROMPTS = [
  'What did I note about Aurora?',
  'Summarize my last memory.',
  'What needs approval?',
];

function StatusLine({ ok, text }: { ok?: boolean; text: string }) {
  return (
    <View style={[styles.row, { justifyContent: 'space-between', marginTop: 8 }]}>
      <Text style={styles.itemDesc}>{text}</Text>
      <Pill tone={ok ? 'ok' : undefined} text={ok ? 'ready' : 'idle'} />
    </View>
  );
}

export function AskScreen() {
  const [prompt, setPrompt] = useState(PROMPTS[0]);
  const [mode, setMode] = useState('Local');
  const [out, setOut] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const ask = async () => {
    if (!prompt.trim()) return;
    setBusy(true);
    try {
      setOut(await api.ask(prompt, mode === 'Cloud'));
    } catch (e: any) {
      setOut({ error: String(e.message || e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <GlassCard eyebrow="Sample feature" title="Private Memory Brief" right={<Pill tone="accent" text="React Native" />}>
        <View style={[styles.row, { alignItems: 'stretch', marginBottom: 14 }]}>
          <Metric label="memory" value={out?.sources?.length ? `${out.sources.length}` : '0'} />
          <Metric label="route" value={out?.route || 'local'} tone="ok" />
          <Metric label="saved" value={out?.savings ? `${out.savings.tokens_saved_estimate}` : '--'} tone="warn" />
        </View>

        <Field
          label="Prompt"
          placeholder="Ask your private memory"
          value={prompt}
          onChangeText={setPrompt}
          multiline
        />

        <View style={styles.meta}>
          {PROMPTS.map((item) => (
            <Button key={item} title={item} kind="ghost" onPress={() => setPrompt(item)} />
          ))}
        </View>

        <View style={{ marginTop: 14 }}>
          <SegmentedControl items={['Local', 'Cloud']} value={mode} onChange={setMode} />
        </View>

        <View style={[styles.row, { justifyContent: 'flex-end', marginTop: 14 }]}>
          <Button title={busy ? 'Thinking' : 'Ask Shadow'} onPress={ask} disabled={busy} />
        </View>

        {out?.error ? <Text style={[styles.answer, { borderColor: theme.bad }]}>{out.error}</Text> : null}
        {out && !out.error ? (
          <View>
            <Text style={styles.answer}>{out.answer}</Text>
            <View style={styles.meta}>
              <Pill tone="accent" text={`${out.route === 'frontier' ? 'frontier' : 'on-device'} / ${out.model_used}`} />
              <Pill text={`${(out.sources || []).length} sources`} />
              {out.savings ? <Pill tone="ok" text={`~${out.savings.tokens_saved_estimate} tokens saved`} /> : null}
              {typeof out.grounding === 'number' ? <Pill text={`grounding ${out.grounding}`} /> : null}
            </View>
          </View>
        ) : null}
      </GlassCard>
    </Screen>
  );
}

export function MemoryScreen() {
  const [title, setTitle] = useState('Recruiter demo note');
  const [text, setText] = useState('Project Aurora ships in March; lead is Dana.');
  const [q, setQ] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [status, setStatus] = useState('');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const store = async () => {
    if (!text.trim()) return;
    await api.ingest(text, title || 'Mobile Import');
    setStatus('Memory stored');
  };

  const search = (query: string) => {
    setQ(query);
    if (timer.current) clearTimeout(timer.current);
    if (!query.trim()) {
      setResults([]);
      return;
    }
    timer.current = setTimeout(async () => {
      try {
        setResults(await api.search(query));
      } catch {
        setResults([]);
      }
    }, 300);
  };

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  return (
    <Screen>
      <GlassCard eyebrow="Capture" title="Memory capsule" right={<Pill tone="ok" text={status || 'encrypted'} />}>
        <Field label="Source" placeholder="Project notes" value={title} onChangeText={setTitle} />
        <Field
          label="Memory"
          placeholder="Paste a short note"
          value={text}
          onChangeText={setText}
          multiline
        />
        <Button title="Store memory" onPress={store} />
      </GlassCard>

      <GlassCard eyebrow="Recall" title="Search memory">
        <Field placeholder="Search Aurora, Dana, March..." value={q} onChangeText={search} />
        {results.length === 0 ? <Text style={styles.empty}>No matching memory yet.</Text> : results.map((r, i) => (
          <View key={`${r.item?.id || 'memory'}-${i}`} style={styles.item}>
            <Text style={styles.itemTitle}>{r.item.source.title}</Text>
            <Text style={styles.itemDesc}>{r.item.text}</Text>
            <View style={styles.meta}>
              <Pill tone="ok" text={`conf ${(r.item.confidence || 0).toFixed(2)}`} />
              <Pill text={r.item.category} />
            </View>
          </View>
        ))}
      </GlassCard>
    </Screen>
  );
}

const TOOLS = [
  { tool: 'note.create', label: 'Note', fields: [['title', 'Title'], ['body', 'Body']] },
  { tool: 'reminder.create', label: 'Reminder', fields: [['text', 'Reminder'], ['when', 'When']] },
  { tool: 'http.get', label: 'Fetch', fields: [['url', 'URL']] },
] as const;

export function ActionsScreen() {
  const [sel, setSel] = useState(0);
  const [params, setParams] = useState<Record<string, string>>({});
  const [out, setOut] = useState<any>(null);
  const tool = TOOLS[sel];

  const run = async () => {
    try {
      setOut(await api.execute(tool.tool, params));
    } catch (e: any) {
      setOut({ error: String(e.message || e) });
    }
  };

  return (
    <Screen>
      <GlassCard eyebrow="Approval gate" title="Sandboxed action">
        <SegmentedControl items={TOOLS.map((item) => item.label)} value={tool.label} onChange={(label) => {
          const index = TOOLS.findIndex((item) => item.label === label);
          setSel(index);
          setParams({});
          setOut(null);
        }} />

        <View style={{ marginTop: 14 }}>
          {tool.fields.map(([key, label]) => (
            <Field
              key={key}
              label={label}
              placeholder={label}
              value={params[key] || ''}
              onChangeText={(value) => setParams({ ...params, [key]: value })}
            />
          ))}
        </View>

        <Button title="Execute once" onPress={run} />
        {out ? <Text style={[styles.answer, out.error && { borderColor: theme.bad }]}>{JSON.stringify(out, null, 2)}</Text> : null}
      </GlassCard>
    </Screen>
  );
}

export function ModelsScreen() {
  const [data, setData] = useState<any>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});

  const load = async () => {
    try {
      setData(await api.providers());
    } catch (e: any) {
      setData({ error: String(e.message || e) });
    }
  };

  useEffect(() => { load(); }, []);

  const connect = async (name: string) => {
    if (!keys[name]) return;
    await api.connectProvider(name, keys[name]);
    setKeys({ ...keys, [name]: '' });
    load();
  };

  const disconnect = async (name: string) => {
    await api.disconnectProvider(name);
    load();
  };

  return (
    <Screen>
      <GlassCard eyebrow="Frontier routing" title="Provider keys">
        {data?.providers?.length ? data.providers.map((p: any) => (
          <View key={p.provider} style={styles.item}>
            <View style={[styles.row, { justifyContent: 'space-between' }]}>
              <Text style={styles.itemTitle}>{p.label}</Text>
              <Pill tone={p.connected ? 'ok' : undefined} text={p.connected ? 'connected' : 'not connected'} />
            </View>
            <Text style={styles.itemDesc}>{p.note}</Text>
            {p.connected ? (
              <View style={{ marginTop: 10 }}>
                <Button title="Disconnect" kind="danger" onPress={() => disconnect(p.provider)} />
              </View>
            ) : (
              <View style={{ marginTop: 10 }}>
                <Field
                  placeholder="API key"
                  secureTextEntry
                  value={keys[p.provider] || ''}
                  onChangeText={(value) => setKeys({ ...keys, [p.provider]: value })}
                />
                <Button title="Connect" onPress={() => connect(p.provider)} />
              </View>
            )}
          </View>
        )) : <Text style={styles.empty}>Pair with a node to load providers.</Text>}
      </GlassCard>
    </Screen>
  );
}

export function ApprovalsScreen() {
  const [items, setItems] = useState<any[]>([]);

  const load = async () => {
    try {
      setItems((await api.approvals()).filter((a: any) => a.status === 'pending'));
    } catch {
      setItems([]);
    }
  };

  useEffect(() => { load(); }, []);

  const decide = async (id: string, ok: boolean) => {
    await api.decide(id, ok);
    load();
  };

  return (
    <Screen>
      <GlassCard eyebrow="Decisions" title="Pending approvals">
        {items.length === 0 ? <Text style={styles.empty}>Nothing waiting.</Text> : items.map((a) => (
          <View key={a.id} style={styles.item}>
            <View style={[styles.row, { justifyContent: 'space-between' }]}>
              <Text style={styles.itemTitle}>{a.action.tool_name}</Text>
              <Pill tone={a.risk_label === 'low' ? 'ok' : 'bad'} text={a.risk_label} />
            </View>
            <Text style={styles.itemDesc}>{a.action.description}</Text>
            <View style={[styles.row, { marginTop: 10 }]}>
              <Button title="Approve" onPress={() => decide(a.id, true)} wide />
              <Button title="Deny" kind="danger" onPress={() => decide(a.id, false)} wide />
            </View>
          </View>
        ))}
      </GlassCard>
    </Screen>
  );
}

export function AuditScreen() {
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    (async () => {
      try {
        setItems((await api.audit()).slice(-40).reverse());
      } catch {
        setItems([]);
      }
    })();
  }, []);

  return (
    <Screen>
      <GlassCard eyebrow="Trace" title="Audit log">
        {items.length === 0 ? <Text style={styles.empty}>No events yet.</Text> : items.map((e, i) => (
          <View key={`${e.id || 'audit'}-${i}`} style={[styles.row, { justifyContent: 'space-between', paddingVertical: 9 }]}>
            <Text style={[styles.itemTitle, { flex: 1 }]} numberOfLines={1}>{e.event_type}</Text>
            <Pill tone={e.status === 'blocked' ? 'bad' : e.status === 'answered' || e.status === 'allowed' ? 'ok' : undefined} text={e.status} />
          </View>
        ))}
      </GlassCard>
    </Screen>
  );
}

export function SettingsScreen() {
  const [url, setUrl] = useState(getBaseUrl());
  const [paired, setPaired] = useState(isPaired());
  const [status, setStatus] = useState<string>('');

  const save = async () => {
    const saved = await setBaseUrl(url);
    setUrl(saved);
    setStatus('Saved');
  };

  const test = async () => {
    try {
      const h = await api.health();
      setStatus(`Connected to node ${h.version}`);
    } catch (e: any) {
      setStatus('Cannot reach node: ' + String(e.message || e));
    }
  };

  const doPair = async () => {
    try {
      await setBaseUrl(url);
      await pairDevice('Shadow Native');
      setPaired(true);
      setStatus('Paired with signed requests');
    } catch (e: any) {
      setStatus('Pairing failed: ' + String(e.message || e));
    }
  };

  const doUnpair = async () => {
    await unpair();
    setPaired(false);
    setStatus('Unpaired');
  };

  const summary = useMemo(() => paired ? 'Signed transport enabled' : 'Pairing required for protected routes', [paired]);

  return (
    <Screen>
      <GlassCard eyebrow="Connection" title="Shadow Node" right={<Pill tone={paired ? 'ok' : undefined} text={paired ? 'paired' : 'not paired'} />}>
        <Field
          label="Base URL"
          placeholder="http://localhost:8787"
          autoCapitalize="none"
          autoCorrect={false}
          value={url}
          onChangeText={setUrl}
        />
        <View style={[styles.row, { flexWrap: 'wrap' }]}>
          <Button title="Save" onPress={save} />
          <Button title="Test" kind="ghost" onPress={test} />
          {paired ? <Button title="Unpair" kind="danger" onPress={doUnpair} /> : <Button title="Pair device" onPress={doPair} />}
        </View>
        <StatusLine ok={paired} text={status || summary} />
      </GlassCard>
    </Screen>
  );
}
