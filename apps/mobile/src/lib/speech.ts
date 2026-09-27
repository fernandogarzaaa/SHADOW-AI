/**
 * Spoken playback for assistant messages (Phase 6).
 *
 * Two paths: the node's server TTS (POST /voice/speak audio, played with
 * expo-av) when the user prefers it and the node reports a TTS provider,
 * otherwise the device's own voice via expo-speech. Server failures always
 * fall back to device speech instead of surfacing an error.
 */

import { Audio } from "expo-av";
import * as FileSystem from "expo-file-system/legacy";
import * as Speech from "expo-speech";
import {
	getVoiceCapabilities,
	synthesizeSpeech,
	ShadowApiError,
} from "@/api/shadow";
import { bytesToBase64 } from "./base64";

export interface SpeakOptions {
	rate: number;
	pitch: number;
	preferServerTts: boolean;
}

/** Session cache: null until the first capabilities fetch. */
let serverTtsAvailable: boolean | null = null;
let currentSound: Audio.Sound | null = null;

export async function refreshServerTtsAvailability(): Promise<boolean> {
	try {
		const caps = await getVoiceCapabilities();
		serverTtsAvailable = caps.tts.available;
	} catch {
		// Not paired, or the node is unreachable: no server TTS.
		serverTtsAvailable = false;
	}
	return serverTtsAvailable;
}

/** True once the node has confirmed a TTS provider (cached per session). */
export async function isServerTtsAvailable(): Promise<boolean> {
	if (serverTtsAvailable === null) {
		await refreshServerTtsAvailability();
	}
	return serverTtsAvailable === true;
}

async function unloadCurrentSound(): Promise<void> {
	const sound = currentSound;
	currentSound = null;
	if (sound) {
		try {
			sound.setOnPlaybackStatusUpdate(null);
			await sound.unloadAsync();
		} catch {
			// best-effort
		}
	}
}

/** Stop any in-flight speech, server or device. */
export async function stopSpeaking(): Promise<void> {
	await unloadCurrentSound();
	try {
		const speaking = await Speech.isSpeakingAsync();
		if (speaking) await Speech.stop();
	} catch {
		// best-effort
	}
}

/**
 * Download server TTS audio for the text to the app cache and return a
 * playable file URI. Throws on 503 (no provider) and other failures.
 */
async function downloadServerTtsAudio(text: string): Promise<string> {
	const { data } = await synthesizeSpeech(text);
	const base64 = bytesToBase64(new Uint8Array(data));
	const dir = `${FileSystem.cacheDirectory}shadow-tts`;
	try {
		await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
	} catch {
		// already exists
	}
	const fileUri = `${dir}/speak-${Date.now()}.mp3`;
	await FileSystem.writeAsStringAsync(fileUri, base64, {
		encoding: FileSystem.EncodingType.Base64,
	});
	return fileUri;
}

async function speakViaServer(
	text: string,
	onEnd: () => void,
): Promise<boolean> {
	let fileUri: string;
	try {
		fileUri = await downloadServerTtsAudio(text);
	} catch (e) {
		// 503 means the provider went away mid-session: stop asking the
		// node for speech and fall back to the device voice below.
		if (e instanceof ShadowApiError && e.status === 503) {
			serverTtsAvailable = false;
		}
		return false;
	}
	try {
		await Audio.setAudioModeAsync({ playsInSilentModeIOS: true });
		const { sound } = await Audio.Sound.createAsync(
			{ uri: fileUri },
			{ shouldPlay: true },
		);
		currentSound = sound;
		sound.setOnPlaybackStatusUpdate((status) => {
			if (status.isLoaded && status.didJustFinish) {
				onEnd();
				void unloadCurrentSound();
			}
		});
		return true;
	} catch {
		return false;
	}
}

function speakViaDevice(
	text: string,
	opts: SpeakOptions,
	onEnd: () => void,
): void {
	Speech.speak(text, {
		rate: opts.rate,
		pitch: opts.pitch,
		onDone: onEnd,
		onStopped: onEnd,
		onError: onEnd,
	});
}

/**
 * Speak the text. Uses server TTS when preferred and available, otherwise
 * the device voice. onEnd fires when playback finishes or is stopped.
 */
export async function speakText(
	text: string,
	opts: SpeakOptions,
	onEnd: () => void,
): Promise<void> {
	await stopSpeaking();
	const trimmed = text.trim();
	if (!trimmed) {
		onEnd();
		return;
	}
	// Keep clips short: TTS providers bill per character and long
	// messages are unpleasant to listen to.
	const clip = trimmed.length > 1200 ? `${trimmed.slice(0, 1200)}` : trimmed;
	if (opts.preferServerTts && (await isServerTtsAvailable())) {
		const played = await speakViaServer(clip, onEnd);
		if (played) return;
	}
	speakViaDevice(clip, opts, onEnd);
}
