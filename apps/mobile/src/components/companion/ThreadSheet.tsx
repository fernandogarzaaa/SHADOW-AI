import BottomSheet from "@gorhom/bottom-sheet";
import * as Haptics from "expo-haptics";
import { forwardRef, useMemo } from "react";
import {
	FlatList,
	Pressable,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { Sheet, SheetView } from "@/components/ui/sheet";
import { AgentMark } from "@/components/companion/AgentMark";
import { ShadowAvatar } from "@/components/Avatar";
import { getProvider } from "@/providers";
import { useChatStore, type ChatThread } from "@/stores/useChatStore";
import { useProfileStore } from "@/stores/useProfileStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";

interface ThreadSheetProps {
	onSelect: (threadId: string) => void;
	onNewThread: () => void;
}

function formatDate(ts: number): string {
	const d = new Date(ts);
	const now = new Date();
	const sameDay = d.toDateString() === now.toDateString();
	if (sameDay) {
		return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
	}
	return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export const ThreadSheet = forwardRef<BottomSheet, ThreadSheetProps>(
	function ThreadSheet({ onSelect, onNewThread }, ref) {
		const { colors } = useTheme();
		const { threads, activeThreadId, deleteThread } = useChatStore();
		const avatarId = useProfileStore((s) => s.profile.avatarId);

		const snapPoints = useMemo(() => ["70%", "92%"], []);

		function renderThread({ item }: { item: ChatThread }) {
			const active = item.id === activeThreadId;
			const provider = getProvider(item.providerId);
			const modelLabel =
				provider.models.find((m) => m.id === item.modelId)?.label ?? item.modelId;
			const preview = item.messages[item.messages.length - 1]?.text.slice(0, 80);

			return (
				<Pressable
					onPress={() => {
						Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
						onSelect(item.id);
					}}
					style={({ pressed }) => [
						styles.thread,
						{
							opacity: pressed ? 0.6 : 1,
							backgroundColor: active ? colors.userBubble : "transparent",
						},
					]}
					accessibilityRole="button"
					accessibilityLabel={`Open chat: ${item.title}${active ? ", current chat" : ""}`}
				>
					<ShadowAvatar avatarId={avatarId} size={36} />
					<View style={styles.threadText}>
						<Text
							style={[
								typography.body,
								{
									color: colors.foreground,
									fontWeight: active ? "700" : "600",
								},
							]}
							numberOfLines={1}
						>
							{item.title}
						</Text>
						<Text
							style={[typography.meta, { color: colors.mutedForeground }]}
							numberOfLines={1}
						>
							{provider.label} · {modelLabel}
							{preview ? ` · ${preview}` : ""}
						</Text>
					</View>
					<Text style={[typography.meta, { color: colors.mutedForeground }]}>
						{formatDate(item.updatedAt)}
					</Text>
					<Pressable
						onPress={() => {
							Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
							void deleteThread(item.id);
						}}
						hitSlop={12}
						style={({ pressed }) => [
							styles.deleteButton,
							{ opacity: pressed ? 0.6 : 1 },
						]}
						accessibilityRole="button"
						accessibilityLabel={`Delete chat: ${item.title}`}
					>
						<Text style={[typography.meta, { color: colors.destructive }]}>
							Delete
						</Text>
					</Pressable>
				</Pressable>
			);
		}

		return (
			<Sheet ref={ref} snapPoints={snapPoints}>
				<SheetView>
					<View style={styles.header}>
						<Text style={[typography.h2, { color: colors.foreground }]}>
							Chats
						</Text>
						<Pressable
							onPress={() => {
								Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
								onNewThread();
							}}
							style={({ pressed }) => [
								styles.newButton,
								{
									backgroundColor: colors.primary,
									opacity: pressed ? 0.85 : 1,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel="Start a new chat"
						>
							<Text
								style={[typography.uiLabel, { color: colors.primaryForeground, fontWeight: "700" }]}
							>
								New chat
							</Text>
						</Pressable>
					</View>
					<FlatList
						data={threads}
						keyExtractor={(t) => t.id}
						renderItem={renderThread}
						ItemSeparatorComponent={() => (
							<View style={[styles.separator, { backgroundColor: colors.border }]} />
						)}
						ListEmptyComponent={
							<View style={styles.emptyState}>
								<AgentMark size={56} />
								<Text style={[typography.h2, { color: colors.foreground, textAlign: "center" }]}>
									No chats yet
								</Text>
								<Text
									style={[
										typography.body,
										{
											color: colors.mutedForeground,
											textAlign: "center",
											marginTop: Spacing.sm,
										},
									]}
								>
									Start a conversation and it will show up here.
								</Text>
								<Pressable
									onPress={() => {
										Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
										onNewThread();
									}}
									style={({ pressed }) => [
										styles.emptyButton,
										{
											backgroundColor: colors.primary,
											opacity: pressed ? 0.85 : 1,
										},
									]}
									accessibilityRole="button"
									accessibilityLabel="Start your first chat"
								>
									<Text
										style={[
											typography.uiLabel,
											{ color: colors.primaryForeground, fontWeight: "700" },
										]}
									>
										Start a chat
									</Text>
								</Pressable>
							</View>
						}
					/>
				</SheetView>
			</Sheet>
		);
	},
);

const styles = StyleSheet.create({
	header: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		paddingHorizontal: Spacing.lg,
		paddingBottom: Spacing.md,
	},
	newButton: {
		borderRadius: SemanticSpacing.radiusModal,
		paddingHorizontal: Spacing.md,
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
	},
	thread: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingHorizontal: Spacing.lg,
		paddingVertical: Spacing.sm,
		minHeight: 60,
		borderRadius: SemanticSpacing.radiusCard,
		marginHorizontal: Spacing.sm,
	},
	threadText: {
		flex: 1,
		gap: 2,
	},
	deleteButton: {
		minHeight: SemanticSpacing.buttonHeightMd,
		justifyContent: "center",
		paddingHorizontal: Spacing.sm,
	},
	separator: {
		height: StyleSheet.hairlineWidth,
		marginHorizontal: Spacing.lg,
	},
	emptyState: {
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.xl,
		gap: Spacing.sm,
	},
	emptyButton: {
		marginTop: Spacing.md,
		borderRadius: SemanticSpacing.radiusModal,
		paddingHorizontal: Spacing.xl,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
	},
});
