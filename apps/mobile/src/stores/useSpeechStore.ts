/**
 * Which assistant message is currently being spoken, shared across all
 * MessageView instances so only one speaker toggle is active at a time.
 */

import { create } from "zustand";
import { speakText, stopSpeaking } from "@/lib/speech";
import { useVoiceSettingsStore } from "./useVoiceSettingsStore";

interface SpeechState {
	speakingId: string | null;
	/** Toggle speech for a message: start, or stop if it is the active one. */
	toggle: (id: string, text: string) => Promise<void>;
	stop: () => Promise<void>;
}

export const useSpeechStore = create<SpeechState>()((set, get) => ({
	speakingId: null,

	toggle: async (id, text) => {
		if (get().speakingId === id) {
			await get().stop();
			return;
		}
		await stopSpeaking();
		const settings = useVoiceSettingsStore.getState();
		if (!settings.ttsEnabled) return;
		set({ speakingId: id });
		const clearIfCurrent = () => {
			if (useSpeechStore.getState().speakingId === id) {
				set({ speakingId: null });
			}
		};
		try {
			await speakText(
				text,
				{
					rate: settings.speechRate,
					pitch: settings.speechPitch,
					preferServerTts: settings.preferServerTts,
				},
				clearIfCurrent,
			);
		} catch {
			clearIfCurrent();
		}
	},

	stop: async () => {
		await stopSpeaking();
		set({ speakingId: null });
	},
}));
