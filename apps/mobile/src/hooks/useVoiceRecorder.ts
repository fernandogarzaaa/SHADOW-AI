/**
 * Microphone recording for the composer (Phase 6).
 *
 * Records with expo-av, then the caller uploads the file to
 * POST /voice/transcribe. Permission is requested at record time; a
 * denial shows where to re-enable it instead of failing silently.
 */

import { Audio } from "expo-av";
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Linking } from "react-native";

export interface VoiceRecorder {
	recording: boolean;
	transcribing: boolean;
	elapsedSeconds: number;
	start: () => Promise<boolean>;
	/** Stops and returns the recording file URI, or null if none. */
	stop: () => Promise<string | null>;
	cancel: () => Promise<void>;
	setTranscribing: (value: boolean) => void;
}

export function useVoiceRecorder(): VoiceRecorder {
	const [recording, setRecording] = useState(false);
	const [transcribing, setTranscribing] = useState(false);
	const [elapsedSeconds, setElapsedSeconds] = useState(0);
	const recordingRef = useRef<Audio.Recording | null>(null);
	const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

	const clearTimer = () => {
		if (timerRef.current) {
			clearInterval(timerRef.current);
			timerRef.current = null;
		}
	};

	// If the composer unmounts mid-recording, stop the native recording
	// rather than leaving the microphone open.
	useEffect(
		() => () => {
			clearTimer();
			const rec = recordingRef.current;
			recordingRef.current = null;
			if (rec) {
				rec.stopAndUnloadAsync().catch(() => {});
			}
		},
		[],
	);

	const start = useCallback(async (): Promise<boolean> => {
		if (recordingRef.current) return true;
		const permission = await Audio.requestPermissionsAsync();
		if (permission.status !== "granted") {
			Alert.alert(
				"Microphone off",
				"SHADOW needs microphone access to turn your voice into text. Enable it in your device settings, then try again.",
				[
					{ text: "Not now", style: "cancel" },
					{ text: "Open settings", onPress: () => void Linking.openSettings() },
				],
			);
			return false;
		}
		try {
			await Audio.setAudioModeAsync({
				allowsRecordingIOS: true,
				playsInSilentModeIOS: true,
			});
			const { recording: rec } = await Audio.Recording.createAsync(
				Audio.RecordingOptionsPresets.HIGH_QUALITY,
			);
			recordingRef.current = rec;
			setElapsedSeconds(0);
			setRecording(true);
			timerRef.current = setInterval(() => {
				setElapsedSeconds((s) => s + 1);
			}, 1000);
			return true;
		} catch {
			Alert.alert(
				"Could not record",
				"The microphone did not start. Try again.",
			);
			recordingRef.current = null;
			return false;
		}
	}, []);

	const finish = useCallback(
		async (keep: boolean): Promise<string | null> => {
			const rec = recordingRef.current;
			recordingRef.current = null;
			clearTimer();
			setRecording(false);
			if (!rec) return null;
			try {
				await rec.stopAndUnloadAsync();
			} catch {
				// already stopped
			}
			try {
				await Audio.setAudioModeAsync({ allowsRecordingIOS: false });
			} catch {
				// best-effort
			}
			if (!keep) return null;
			return rec.getURI();
		},
		[],
	);

	const stop = useCallback(() => finish(true), [finish]);
	const cancel = useCallback(async () => {
		await finish(false);
	}, [finish]);

	return {
		recording,
		transcribing,
		elapsedSeconds,
		start,
		stop,
		cancel,
		setTranscribing,
	};
}
