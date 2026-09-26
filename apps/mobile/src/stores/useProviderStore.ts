/**
 * Active provider/model selection.
 *
 * Persists the choice (never the key) in AsyncStorage. Key presence is
 * checked against SecureStore at startup and whenever the provider
 * changes: a provider without a saved key cannot be active.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import {
	DEFAULT_PROVIDER,
	KEY_PROVIDERS,
	getDefaultModel,
	getProvider,
	hasProviderKey,
} from "@/providers";
import type { ProviderId } from "@/providers";
import { useConnectionStore } from "@/stores/useConnectionStore";

const STORAGE_KEY = "shadow.provider.selection.v1";

interface Selection {
	providerId: ProviderId;
	models: Partial<Record<ProviderId, string>>;
}

interface ProviderStoreState {
	providerId: ProviderId;
	modelId: string;
	initialized: boolean;
	/** Providers (key-based) that currently have a key saved. */
	keyedProviders: ProviderId[];
	initialize: () => Promise<void>;
	refreshKeyPresence: () => Promise<void>;
	setProvider: (providerId: ProviderId) => Promise<void>;
	setModel: (modelId: string) => Promise<void>;
}

async function readSelection(): Promise<Selection | null> {
	try {
		const raw = await AsyncStorage.getItem(STORAGE_KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as Selection;
		if (!parsed || typeof parsed.providerId !== "string") return null;
		return parsed;
	} catch {
		return null;
	}
}

async function writeSelection(selection: Selection): Promise<void> {
	try {
		await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
	} catch {
		// Selection persistence is best-effort.
	}
}

export const useProviderStore = create<ProviderStoreState>()((set, get) => ({
	providerId: DEFAULT_PROVIDER,
	modelId: getDefaultModel(DEFAULT_PROVIDER),
	initialized: false,
	keyedProviders: [],

	initialize: async () => {
		const keyed = (
			await Promise.all(
				KEY_PROVIDERS.map(async (p) => ((await hasProviderKey(p).catch(() => false)) ? p : null)),
			)
		).filter((p): p is ProviderId => p !== null);

		const saved = await readSelection();
		let providerId = DEFAULT_PROVIDER;
		let modelId = getDefaultModel(DEFAULT_PROVIDER);
		const models: Partial<Record<ProviderId, string>> = {};

		if (saved) {
			for (const p of KEY_PROVIDERS) {
				if (saved.models[p]) models[p] = saved.models[p];
			}
			// Honor the saved provider only when it still has a key.
			if (keyed.includes(saved.providerId)) {
				providerId = saved.providerId;
			} else if (keyed.length > 0) {
				providerId = keyed[0];
			}
		} else if (keyed.length > 0) {
			providerId = keyed[0];
		}
		modelId = models[providerId] ?? getDefaultModel(providerId);

		await writeSelection({ providerId, models });
		set({ providerId, modelId, keyedProviders: keyed, initialized: true });
	},

	refreshKeyPresence: async () => {
		const keyed = (
			await Promise.all(
				KEY_PROVIDERS.map(async (p) => ((await hasProviderKey(p).catch(() => false)) ? p : null)),
			)
		).filter((p): p is ProviderId => p !== null);
		const { providerId } = get();
		if (!keyed.includes(providerId)) {
			// Active key was removed: fall back to another keyed provider,
			// the linked node, or the default last.
			const nodePaired = useConnectionStore.getState().isPaired;
			const fallback = keyed[0] ?? (nodePaired ? ("node" as ProviderId) : DEFAULT_PROVIDER);
			await get().setProvider(fallback);
		}
		set({ keyedProviders: keyed });
	},

	setProvider: async (providerId: ProviderId) => {
		const models = { ...(await readSelection())?.models };
		const modelId = models[providerId] ?? getDefaultModel(providerId);
		await writeSelection({ providerId, models });
		set({ providerId, modelId });
	},

	setModel: async (modelId: string) => {
		const { providerId } = get();
		const saved = await readSelection();
		const models = { ...(saved?.models), [providerId]: modelId };
		const provider = getProvider(providerId);
		if (!provider.models.some((m) => m.id === modelId)) {
			return;
		}
		await writeSelection({ providerId, models });
		set({ modelId });
	},
}));
