/**
 * Voice preferences (Phase 6).
 *
 * Non-sensitive local settings, so AsyncStorage (not SecureStore) is the
 * right home, matching the theme-mode pattern. TTS playback prefers the
 * node's server TTS when the toggle is on and the node reports a TTS
 * provider; otherwise the device speaks via expo-speech.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";

const STORAGE_KEY = "shadow.voice.v1";

export const MIN_SPEECH_RATE = 0.5;
export const MAX_SPEECH_RATE = 2.0;
export const MIN_SPEECH_PITCH = 0.5;
export const MAX_SPEECH_PITCH = 2.0;

export interface VoiceSettings {
	/** Master switch for the speaker button on assistant messages. */
	ttsEnabled: boolean;
	/** expo-speech rate, 0.5 to 2.0. */
	speechRate: number;
	/** expo-speech pitch, 0.5 to 2.0. */
	speechPitch: number;
	/** Use POST /voice/speak audio when the node has a TTS provider. */
	preferServerTts: boolean;
}

const DEFAULTS: VoiceSettings = {
	ttsEnabled: true,
	speechRate: 1.0,
	speechPitch: 1.0,
	preferServerTts: true,
};

function clamp(n: number, min: number, max: number): number {
	return Math.min(max, Math.max(min, n));
}

function sanitize(parsed: Partial<VoiceSettings>): VoiceSettings {
	return {
		ttsEnabled:
			typeof parsed.ttsEnabled === "boolean" ? parsed.ttsEnabled : DEFAULTS.ttsEnabled,
		speechRate:
			typeof parsed.speechRate === "number"
				? clamp(parsed.speechRate, MIN_SPEECH_RATE, MAX_SPEECH_RATE)
				: DEFAULTS.speechRate,
		speechPitch:
			typeof parsed.speechPitch === "number"
				? clamp(parsed.speechPitch, MIN_SPEECH_PITCH, MAX_SPEECH_PITCH)
				: DEFAULTS.speechPitch,
		preferServerTts:
			typeof parsed.preferServerTts === "boolean"
				? parsed.preferServerTts
				: DEFAULTS.preferServerTts,
	};
}

interface VoiceSettingsState extends VoiceSettings {
	initialized: boolean;
	initialize: () => Promise<void>;
	save: (patch: Partial<VoiceSettings>) => Promise<void>;
}

async function persist(settings: VoiceSettings): Promise<void> {
	try {
		await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
	} catch {
		// best-effort
	}
}

export const useVoiceSettingsStore = create<VoiceSettingsState>()((set, get) => ({
	...DEFAULTS,
	initialized: false,

	initialize: async () => {
		try {
			const raw = await AsyncStorage.getItem(STORAGE_KEY);
			if (raw) {
				set({ ...sanitize(JSON.parse(raw) as Partial<VoiceSettings>), initialized: true });
				return;
			}
		} catch {
			// fall through to defaults
		}
		set({ initialized: true });
	},

	save: async (patch) => {
		const next = sanitize({ ...get(), ...patch });
		set(next);
		await persist(next);
	},
}));
