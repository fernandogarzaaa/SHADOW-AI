import React, { useEffect, useState } from 'react';
import { View, Text, ScrollView } from 'react-native';
import { api } from './api';
import { theme } from './theme';
import { Card, Field, Button, Pill, styles } from './ui';

export function AskScreen() {
  const [prompt, setPrompt] = useState('');
  const [cloud, setCloud] = useState(false);
  const [out, setOut] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const ask = async () => {
    if (!prompt.trim()) return;
    setBusy(true);
    try { setOut(await api.ask(prompt, cloud)); } catch (e: any) { setOut({ error: String(e.message || e) }); }
    setBusy(false);
  };
  return (
    <Card title="Ask Shadow" hint="Answers are grounded in your local memory. Retrieved context is treated as untrusted.">
      <Field placeholder="What did I note about the Aurora project?" value={prompt} onChangeText={setPrompt} multiline />
      <View style={[styles.row, { justifyContent: 'space-between' }]}>
        <Button title={cloud ? 'cloud: on' : 'cloud: off'} kind="ghost" onPress={() => setCloud(!cloud)} />
        <Button title={busy ? '…' : 'Ask'} onPress={ask} disabled={busy} />
      </View>
      {out?.error ? <Text style={[styles.answer, { borderColor: theme.bad }]}>{out.error}</Text> : null}
      {out && !out.error ? (
        <View>
          <Text style={styles.answer}>{out.answer}</Text>
          <View style={styles.meta}>
            <Pill text={`${out.route === 'frontier' ? 'frontier' : 'on-device'} · ${out.model_used}`} />
            <Pill text={`${(out.sources || []).length} sources`} />
            {out.savings ? <Pill tone="ok" text={`~${out.savings.tokens_saved_estimate} tokens saved`} /> : null}
            {typeof out.grounding === 'number' ? <Pill text={`grounding ${out.grounding}`} /> : null}
          </View>
        </View>
      ) : null}
    </Card>
  );
}

export function MemoryScreen() {
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [q, setQ] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const store = async () => { if (!text.trim()) return; await api.ingest(text, title || 'Mobile Import'); setText(''); };
  const search = async (query: string) => { setQ(query); if (!query.trim()) return setResults([]); try { setResults(await api.search(query)); } catch { setResults([]); } };
  return (
    <View>
      <Card title="Ingest memory" hint="Stored encrypted on the node. Sensitive content is auto-flagged.">
        <Field label="Source title" placeholder="Project notes" value={title} onChangeText={setTitle} />
        <Field placeholder="Paste text to remember…" value={text} onChangeText={setText} multiline />
        <Button title="Store" onPress={store} />
      </Card>
      <Card title="Search">
        <Field placeholder="Search your memory…" value={q} onChangeText={search} />
        {results.length === 0 ? <Text style={styles.empty}>Results appear here.</Text> : results.map((r, i) => (
          <View key={i} style={styles.item}>
            <Text style={styles.itemTitle}>{r.item.source.title}</Text>
            <Text style={styles.itemDesc}>{r.item.text}</Text>
            <View style={styles.meta}><Pill text={`conf ${(r.item.confidence || 0).toFixed(2)}`} /><Pill text={r.item.category} /></View>
          </View>
        ))}
      </Card>
    </View>
  );
}

const TOOLS = [
  { tool: 'note.create', fields: [['title', 'Title'], ['body', 'Body']] },
  { tool: 'reminder.create', fields: [['text', 'Reminder'], ['when', 'When']] },
  { tool: 'http.get', fields: [['url', 'https://example.com']] },
];

export function ActionsScreen() {
  const [sel, setSel] = useState(0);
  const [params, setParams] = useState<Record<string, string>>({});
  const [out, setOut] = useState<any>(null);
  const run = async () => { try { setOut(await api.execute(TOOLS[sel].tool, params)); } catch (e: any) { setOut({ error: String(e.message || e) }); } };
  return (
    <Card title="Run an action" hint="Real, sandboxed actions behind the approval gate.">
      <View style={[styles.meta, { marginBottom: 12 }]}>
        {TOOLS.map((t, i) => <Button key={t.tool} title={t.tool} kind={i === sel ? 'primary' : 'ghost'} onPress={() => { setSel(i); setParams({}); }} />)}
      </View>
      {TOOLS[sel].fields.map(([k, ph]) => (
        <Field key={k} label={ph} placeholder={ph} value={params[k] || ''} onChangeText={(v) => setParams({ ...params, [k]: v })} />
      ))}
      <Button title="Execute" onPress={run} />
      {out ? <Text style={[styles.answer, out.error && { borderColor: theme.bad }]}>{JSON.stringify(out, null, 2)}</Text> : null}
    </Card>
  );
}

export function ModelsScreen() {
  const [data, setData] = useState<any>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const load = async () => { try { setData(await api.providers()); } catch (e: any) { setData({ error: String(e.message || e) }); } };
  useEffect(() => { load(); }, []);
  const connect = async (name: string) => { if (!keys[name]) return; await api.connectProvider(name, keys[name]); load(); };
  const disconnect = async (name: string) => { await api.disconnectProvider(name); load(); };
  return (
    <Card title="Models" hint="Hybrid local + frontier. Connect a provider with an API key. Consumer chat subscriptions cannot power third-party inference.">
      {data?.providers?.map((p: any) => (
        <View key={p.provider} style={styles.item}>
          <View style={[styles.row, { justifyContent: 'space-between' }]}>
            <Text style={styles.itemTitle}>{p.label}</Text>
            <Pill tone={p.connected ? 'ok' : undefined} text={p.connected ? 'connected' : 'not connected'} />
          </View>
          <Text style={styles.itemDesc}>{p.note}</Text>
          {p.connected ? (
            <View style={{ marginTop: 10 }}><Button title="Disconnect" kind="danger" onPress={() => disconnect(p.provider)} /></View>
          ) : (
            <View style={{ marginTop: 10 }}>
              <Field placeholder="Paste API key" secureTextEntry value={keys[p.provider] || ''} onChangeText={(v) => setKeys({ ...keys, [p.provider]: v })} />
              <Button title="Connect" onPress={() => connect(p.provider)} />
            </View>
          )}
        </View>
      )) || <Text style={styles.empty}>Connect to a node to manage providers.</Text>}
    </Card>
  );
}

export function ApprovalsScreen() {
  const [items, setItems] = useState<any[]>([]);
  const load = async () => { try { setItems((await api.approvals()).filter((a: any) => a.status === 'pending')); } catch { setItems([]); } };
  useEffect(() => { load(); }, []);
  const decide = async (id: string, ok: boolean) => { await api.decide(id, ok); load(); };
  return (
    <Card title="Pending approvals" hint="High-impact actions wait for your explicit decision.">
      {items.length === 0 ? <Text style={styles.empty}>Nothing waiting.</Text> : items.map((a) => (
        <View key={a.id} style={styles.item}>
          <Text style={styles.itemTitle}>{a.action.tool_name} · <Pill tone={a.risk_label === 'low' ? 'ok' : 'bad'} text={a.risk_label} /></Text>
          <Text style={styles.itemDesc}>{a.action.description}</Text>
          <View style={[styles.row, { marginTop: 10 }]}>
            <Button title="Approve" onPress={() => decide(a.id, true)} />
            <Button title="Deny" kind="danger" onPress={() => decide(a.id, false)} />
          </View>
        </View>
      ))}
    </Card>
  );
}

export function AuditScreen() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => { (async () => { try { setItems((await api.audit()).slice(-40).reverse()); } catch { setItems([]); } })(); }, []);
  return (
    <Card title="Audit log" hint="Every decision the node makes is recorded here.">
      {items.length === 0 ? <Text style={styles.empty}>No events yet.</Text> : items.map((e, i) => (
        <View key={i} style={[styles.row, { justifyContent: 'space-between', borderBottomColor: theme.line, borderBottomWidth: 1, paddingVertical: 8 }]}>
          <Text style={{ color: theme.txt, fontSize: 13, fontWeight: '500' }}>{e.event_type}</Text>
          <Pill tone={e.status === 'blocked' ? 'bad' : e.status === 'answered' || e.status === 'allowed' ? 'ok' : undefined} text={e.status} />
        </View>
      ))}
    </Card>
  );
}
