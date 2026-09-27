import Slider from "@react-native-community/slider";
import { useEffect } from "react";
import { StyleSheet, Text, View } from "react-native";
import { SettingsScreen } from "@/components/settings/SettingsScreen";
import {
	SettingsGroup,
	SettingsRow,
} from "@/components/settings/primitives";
import {
	MAX_SPEECH_PITCH,
	MAX_SPEECH_RATE,
	MIN_SPEECH_PITCH,
	MIN_SPEECH_RATE,
	useVoiceSettingsStore,
} from "@/stores/useVoiceSettingsStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

function SliderRow({
	label,
	description,
	value,
	min,
	max,
	onChange,
}: {
	label: string;
	description: string;
	value: number;
	min: number;
	max: number;
	onChange: (v: number) => void;
}) {
	const { colors } = useTheme();
	return (
		<View style={styles.sliderRow}>
			<View style={styles.sliderHeader}>
				<Text style={[typography.body, { color: colors.foreground }]}>
					{label}
				</Text>
				<Text style={[typography.body, { color: colors.mutedForeground }]}>
					{value.toFixed(2)}x
				</Text>
			</View>
			<Slider
				style={styles.slider}
				minimumValue={min}
				maximumValue={max}
				step={0.05}
				value={value}
				onSlidingComplete={onChange}
				minimumTrackTintColor={colors.primary}
				maximumTrackTintColor={colors.border}
				thumbTintColor={colors.primary}
				accessibilityLabel={label}
				accessibilityHint={description}
			/>
			<Text style={[typography.meta, { color: colors.mutedForeground }]}>
				{description}
			</Text>
		</View>
	);
}

/**
 * Voice settings: spoken replies for assistant messages and the mic
 * button in the composer. Persisted locally with AsyncStorage.
 */
export default function VoiceSettingsScreen() {
	const { colors } = useTheme();
	const initialized = useVoiceSettingsStore((s) => s.initialized);
	const ttsEnabled = useVoiceSettingsStore((s) => s.ttsEnabled);
	const speechRate = useVoiceSettingsStore((s) => s.speechRate);
	const speechPitch = useVoiceSettingsStore((s) => s.speechPitch);
	const preferServerTts = useVoiceSettingsStore((s) => s.preferServerTts);
	const initialize = useVoiceSettingsStore((s) => s.initialize);
	const save = useVoiceSettingsStore((s) => s.save);

	useEffect(() => {
		if (!initialized) void initialize();
	}, [initialized, initialize]);

	return (
		<SettingsScreen title="Voice">
			<SettingsGroup>
				<SettingsRow
					title="Speak replies"
					value="Speaker button on assistant messages"
					toggle={ttsEnabled}
					onToggleChange={(v) => void save({ ttsEnabled: v })}
				/>
				<SettingsRow
					title="Use node voice when available"
					value="Higher quality speech from your SHADOW node"
					toggle={preferServerTts}
					onToggleChange={(v) => void save({ preferServerTts: v })}
				/>
			</SettingsGroup>

			<SettingsGroup>
				<View
					style={[
						styles.card,
						{ backgroundColor: colors.card, borderColor: colors.border },
					]}
				>
					<SliderRow
						label="Speech rate"
						description="How fast the voice speaks. Applies to the device voice."
						value={speechRate}
						min={MIN_SPEECH_RATE}
						max={MAX_SPEECH_RATE}
						onChange={(v) => void save({ speechRate: v })}
					/>
				</View>
				<View
					style={[
						styles.card,
						{ backgroundColor: colors.card, borderColor: colors.border },
					]}
				>
					<SliderRow
						label="Speech pitch"
						description="How high or low the voice sounds. Applies to the device voice."
						value={speechPitch}
						min={MIN_SPEECH_PITCH}
						max={MAX_SPEECH_PITCH}
						onChange={(v) => void save({ speechPitch: v })}
					/>
				</View>
			</SettingsGroup>

			<Text
				style={[
					typography.meta,
					{ color: colors.mutedForeground, paddingHorizontal: Spacing.xl },
				]}
			>
				The microphone button in the composer records locally and sends the
				audio to your node for transcription. Microphone access is asked for
				only when you start recording.
			</Text>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
		padding: Spacing.lg,
	},
	sliderRow: {
		gap: Spacing.xs,
	},
	sliderHeader: {
		flexDirection: "row",
		justifyContent: "space-between",
		alignItems: "center",
	},
	slider: {
		width: "100%",
		height: 40,
	},
});
