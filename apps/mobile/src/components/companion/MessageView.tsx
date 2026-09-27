import { memo } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { router } from "expo-router";
import * as Haptics from "expo-haptics";
import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer";
import { MediaFileImage } from "@/components/media/MediaFileImage";
import { DocumentIcon, SpeakerIcon } from "@/components/icons";
import { useThrottledValue } from "@/hooks/useThrottledValue";
import type { ChatMessage } from "@/stores/useChatStore";
import { useProfileStore } from "@/stores/useProfileStore";
import { useSpeechStore } from "@/stores/useSpeechStore";
import { useVoiceSettingsStore } from "@/stores/useVoiceSettingsStore";
import { Spacing, typography, useTheme } from "@/theme";

/**
 * Markdown rendered on a fixed 50 ms cadence while streaming.
 * React.memo with a raw-content comparison means unchanged text never
 * re-renders the markdown tree.
 */
const ThrottledMarkdown = memo(
	function ThrottledMarkdown({ content }: { content: string }) {
		const throttled = useThrottledValue(content, 50);
		return <MarkdownRenderer content={throttled} />;
	},
	(prev, next) => prev.content === next.content,
);

function StreamingCursor() {
	const { colors } = useTheme();
	return <Text style={[styles.cursor, { color: colors.primary }]}>▍</Text>;
}

const ARTIFACT_REF_RE = /artifact:([A-Za-z0-9_-]+)|\/artifacts\/([A-Za-z0-9_-]+)/g;
const MEDIA_REF_RE = /media:([A-Za-z0-9_-]+)/g;

/** All unique artifact ids referenced in the text, in first-seen order. */
function findArtifactRefs(text: string): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const m of text.matchAll(ARTIFACT_REF_RE)) {
		const id = m[1] ?? m[2];
		if (id && !seen.has(id)) {
			seen.add(id);
			out.push(id);
		}
	}
	return out;
}

/** All unique media ids referenced in the text, in first-seen order. */
function findMediaRefs(text: string): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const m of text.matchAll(MEDIA_REF_RE)) {
		if (!seen.has(m[1])) {
			seen.add(m[1]);
			out.push(m[1]);
		}
	}
	return out;
}

function ArtifactChips({ ids }: { ids: string[] }) {
	const { colors } = useTheme();
	if (ids.length === 0) return null;
	return (
		<View style={styles.chipsRow}>
			{ids.map((id) => (
				<Pressable
					key={id}
					onPress={() => {
						void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						router.push(`/artifact/${id}`);
					}}
					style={({ pressed }) => [
						styles.chip,
						{
							backgroundColor: colors.card,
							borderColor: colors.border,
							opacity: pressed ? 0.7 : 1,
						},
					]}
					accessibilityRole="button"
					accessibilityLabel={`Open artifact ${id}`}
				>
					<DocumentIcon size={14} color={colors.primary} />
					<Text
						style={[typography.uiLabel, { color: colors.foreground }]}
						numberOfLines={1}
					>
						Artifact
					</Text>
				</Pressable>
			))}
		</View>
	);
}

function SpeakToggle({ message }: { message: ChatMessage }) {
	const { colors } = useTheme();
	const ttsEnabled = useVoiceSettingsStore((s) => s.ttsEnabled);
	const speakingId = useSpeechStore((s) => s.speakingId);
	const toggle = useSpeechStore((s) => s.toggle);
	if (!ttsEnabled) return null;
	const active = speakingId === message.id;
	return (
		<Pressable
			onPress={() => void toggle(message.id, message.text)}
			style={({ pressed }) => [
				styles.speakButton,
				{
					backgroundColor: active ? colors.primary : colors.muted,
					opacity: pressed ? 0.7 : 1,
				},
			]}
			hitSlop={8}
			accessibilityRole="button"
			accessibilityLabel={active ? "Stop speaking" : "Speak this message"}
			accessibilityState={{ selected: active }}
		>
			<SpeakerIcon
				size={16}
				color={active ? colors.primaryForeground : colors.mutedForeground}
			/>
		</Pressable>
	);
}

export function MessageView({ message }: { message: ChatMessage }) {
	const { colors } = useTheme();
	const agentName = useProfileStore((s) => s.profile.agentName) || "shadow";

	if (message.role === "user") {
		return (
			<View
				style={styles.userRow}
				accessibilityLabel={`You said: ${message.text}`}
			>
				<View
					style={[
						styles.userPill,
						{ backgroundColor: colors.userBubble },
					]}
				>
					<Text style={[typography.body, { color: colors.userBubbleForeground }]}>
						{message.text}
					</Text>
				</View>
			</View>
		);
	}

	const artifactIds = message.streaming ? [] : findArtifactRefs(message.text);
	const mediaIds = message.streaming ? [] : findMediaRefs(message.text);

	return (
		<View
			style={styles.assistantRow}
			accessibilityLabel={`${agentName} said: ${message.text}`}
		>
			<View style={styles.assistantBody}>
				<ThrottledMarkdown content={message.text} />
				{message.streaming ? <StreamingCursor /> : null}
			</View>
			{mediaIds.map((id) => (
				<MediaFileImage
					key={id}
					mediaId={id}
					style={styles.inlineMedia}
					accessibilityLabel="Image from the assistant"
				/>
			))}
			<View style={styles.assistantFooter}>
				<ArtifactChips ids={artifactIds} />
				<SpeakToggle message={message} />
			</View>
			{message.failed ? (
				<Text
					style={[typography.meta, { color: colors.destructive, marginTop: 4 }]}
					accessibilityRole="alert"
				>
					Failed to send. The error is shown above the composer.
				</Text>
			) : null}
		</View>
	);
}

const styles = StyleSheet.create({
	userRow: {
		flexDirection: "row",
		justifyContent: "flex-end",
		paddingHorizontal: Spacing.lg,
		marginVertical: Spacing.xs,
	},
	userPill: {
		maxWidth: "85%",
		borderRadius: 18,
		paddingHorizontal: Spacing.md,
		paddingVertical: 10,
	},
	assistantRow: {
		paddingHorizontal: Spacing.lg,
		marginVertical: Spacing.sm,
	},
	assistantBody: {
		// No bubble: assistant text sits directly on the paper background.
	},
	cursor: {
		fontSize: 16,
		lineHeight: 22,
	},
	assistantFooter: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		marginTop: Spacing.xs,
		gap: Spacing.sm,
	},
	chipsRow: {
		flexDirection: "row",
		flexWrap: "wrap",
		gap: Spacing.sm,
		flex: 1,
	},
	chip: {
		flexDirection: "row",
		alignItems: "center",
		gap: 6,
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: 999,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.xs,
		maxWidth: 180,
	},
	speakButton: {
		width: 32,
		height: 32,
		borderRadius: 16,
		alignItems: "center",
		justifyContent: "center",
	},
	inlineMedia: {
		width: 240,
		height: 240,
		borderRadius: 12,
		marginTop: Spacing.sm,
	},
});
