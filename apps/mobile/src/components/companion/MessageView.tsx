import { memo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { MarkdownRenderer } from "@/components/markdown/MarkdownRenderer";
import { useThrottledValue } from "@/hooks/useThrottledValue";
import type { ChatMessage } from "@/stores/useChatStore";
import { useProfileStore } from "@/stores/useProfileStore";
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

	return (
		<View
			style={styles.assistantRow}
			accessibilityLabel={`${agentName} said: ${message.text}`}
		>
			<View style={styles.assistantBody}>
				<ThrottledMarkdown content={message.text} />
				{message.streaming ? <StreamingCursor /> : null}
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
});
