/**
 * Dynamic model catalog with caching and static fallback.
 *
 * Providers that expose `listModels` (OpenRouter, OpenCode) fetch their
 * live catalog over HTTP. Results are cached in memory for 24h so the
 * model sheet opens instantly on repeat visits. Any failure falls back
 * to the provider's static `models` list, so the UI never breaks when
 * the catalog endpoint is unreachable.
 */

import type { FetchLike, ModelInfo, ModelProvider, ProviderId } from "./types";

const CACHE_TTL_MS = 24 * 60 * 60 * 1000;

interface CacheEntry {
	at: number;
	models: ModelInfo[];
}

const cache = new Map<ProviderId, CacheEntry>();
const inflight = new Map<ProviderId, Promise<ModelInfo[]>>();

export interface CatalogResult {
	models: ModelInfo[];
	/** True when the list came from a live fetch (fresh or cached). */
	live: boolean;
}

/**
 * Tag static fallback entries as such, so the UI can say the list may be
 * stale. Entries that already carry a source keep it.
 */
function tagStatic(models: ModelInfo[]): ModelInfo[] {
	return models.map((m) =>
		m.capabilities?.source
			? m
			: { ...m, capabilities: { ...m.capabilities, source: "static" } },
	);
}

export async function getModels(
	provider: ModelProvider,
	apiKey: string,
	fetchImpl?: FetchLike,
): Promise<CatalogResult> {
	const providerId = provider.id;
	if (!provider.listModels) {
		return { models: tagStatic(provider.models), live: false };
	}

	const hit = cache.get(providerId);
	if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
		return { models: hit.models, live: true };
	}

	const ongoing = inflight.get(providerId);
	if (ongoing) {
		return { models: await ongoing, live: true };
	}

	const pending = (async (): Promise<ModelInfo[]> => {
		try {
			const models = await provider.listModels!(apiKey, fetchImpl);
			if (models.length > 0) {
				cache.set(providerId, { at: Date.now(), models });
			}
			return models;
		} catch {
			// Refresh failed: drop any expired entry so it is never served
			// as fresh, and fall back to the static list.
			cache.delete(providerId);
			return provider.models;
		} finally {
			inflight.delete(providerId);
		}
	})();
	inflight.set(providerId, pending);

	const models = await pending;
	const served = cache.has(providerId) ? models : tagStatic(models);
	return { models: served, live: cache.has(providerId) };
}

/** Clear cached catalogs (e.g. pull-to-refresh). */
export function clearModelCache(providerId?: ProviderId): void {
	if (providerId) {
		cache.delete(providerId);
	} else {
		cache.clear();
	}
}

/**
 * Test-only seam: shift a cache entry's timestamp back so expiry paths can
 * be exercised without waiting out the real TTL.
 */
export function __testAgeCacheEntry(providerId: ProviderId, ageMs: number): void {
	const hit = cache.get(providerId);
	if (hit) {
		cache.set(providerId, { at: hit.at - ageMs, models: hit.models });
	}
}
