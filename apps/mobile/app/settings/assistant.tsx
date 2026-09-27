import * as Haptics from "expo-haptics";
import { useCallback, useEffect, useState } from "react";
import {
	ActivityIndicator,
	Pressable,
	StyleSheet,
	Text,
	TextInput,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { router } from "expo-router";
import {
	getPersona,
	updatePersona,
	ShadowApiError,
	type PersonaProfile,
} from "@/api/shadow";
import { SettingsScreen } from "@/components/settings/primitives";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "../../src/theme";

function formatDate(updatedAt: number): string {
	if (!updatedAt) return "";
	const d = new Date(updatedAt * 1000);
	const mm = String(d.getMonth() + 1).padStart(2, "0");
	const dd = String(d.getDate()).padStart(2, "0");
	const yy = String(d.getFullYear()).slice(2);
	return `${mm}.${dd}.${yy}`;
}

/**
 * Assistant: the node's Cookie-style identity. Name, avatar emoji, vibe,
 * and status live on the node (encrypted at rest) and are shared by every
 * device. The vibe is real behavior: it becomes the assistant's system
 * prompt for frontier-model calls.
 */
export default function AssistantScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const isPaired = useConnectionStore((s) => s.isPaired);

	const [persona, setPersona] = useState<PersonaProfile | null>(null);
	const [loading, setLoading] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [editing, setEditing] = useState(false);
	const [saving, setSaving] = useState(false);

	const [name, setName] = useState("");
	const [emoji, setEmoji] = useState("");
	const [vibe, setVibe] = useState("");
	const [status, setStatus] = useState("");

	const load = useCallback(async () => {
		if (!isPaired) {
			setLoading(false);
			return;
		}
		setLoading(true);
		setError(null);
		try {
			const p = await getPersona();
			setPersona(p);
			setName(p.name);
			setEmoji(p.avatar_emoji);
			setVibe(p.vibe);
			setStatus(p.status);
		} catch (e) {
			setError(
				e instanceof ShadowApiError
					? e.message
					: "Could not load your assistant's identity.",
			);
		} finally {
			setLoading(false);
		}
	}, [isPaired]);

	useEffect(() => {
		void load();
	}, [load]);

	async function handleSave() {
		if (!name.trim()) {
			setError("Give your assistant a name.");
			return;
		}
		setSaving(true);
		setError(null);
		try {
			const p = await updatePersona({
				name: name.trim(),
				avatar_emoji: emoji.trim() || "\u{1F311}",
				vibe: vibe.trim(),
				status: status.trim(),
			});
			setPersona(p);
			setEditing(false);
			void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
		} catch (e) {
			setError(
				e instanceof ShadowApiError
					? e.message
					: "Could not save. Try again.",
			);
		} finally {
			setSaving(false);
		}
	}

	function handleCancel() {
		if (persona) {
			setName(persona.name);
			setEmoji(persona.avatar_emoji);
			setVibe(persona.vibe);
			setStatus(persona.status);
		}
		setError(null);
		setEditing(false);
	}

	const inputStyle = [
		styles.input,
		typography.body,
		{
			color: colors.foreground,
			backgroundColor: colors.card,
			borderColor: colors.border,
		},
	];

	return (
		<SettingsScreen title="Assistant" showClose={false}>
			<View
				style={[
					styles.container,
					{ paddingBottom: Math.max(insets.bottom, Spacing.xl) },
				]}
			>
				{loading ? (
					<ActivityIndicator
						style={styles.center}
						color={colors.primary}
						accessibilityLabel="Loading assistant identity"
					/>
				) : !isPaired ? (
					<View style={styles.center}>
						<Text style={[typography.body, { color: colors.mutedForeground, textAlign: "center" }]}>
							Link your SHADOW node to name your assistant and give
							it a vibe. The identity lives on the node, encrypted.
						</Text>
						<Pressable
							onPress={() => router.push("/settings/link-node")}
							style={({ pressed }) => [
								styles.saveButton,
								{
									backgroundColor: colors.primary,
									opacity: pressed ? 0.85 : 1,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel="Link node"
						>
							<Text
								style={[
									typography.uiLabel,
									{ color: colors.primaryForeground, fontWeight: "700" },
								]}
							>
								Link node
							</Text>
						</Pressable>
					</View>
				) : error && !persona ? (
					<View style={styles.center}>
						<Text style={[typography.body, { color: colors.destructive, textAlign: "center" }]}>
							{error}
						</Text>
						<Pressable
							onPress={() => void load()}
							style={({ pressed }) => [
								styles.saveButton,
								{
									backgroundColor: colors.card,
									borderColor: colors.border,
									borderWidth: StyleSheet.hairlineWidth,
									opacity: pressed ? 0.7 : 1,
								},
							]}
							accessibilityRole="button"
							accessibilityLabel="Retry"
						>
							<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
								Retry
							</Text>
						</Pressable>
					</View>
				) : (
					<>
						<View style={styles.hero}>
							<View
								style={[
									styles.avatarCircle,
									{ backgroundColor: colors.card, borderColor: colors.border },
								]}
							>
								<Text style={styles.avatarEmoji}>
									{editing ? emoji || "\u{1F311}" : (persona?.avatar_emoji ?? "\u{1F311}")}
								</Text>
							</View>
							<Text style={[typography.h1, { color: colors.foreground, marginTop: Spacing.md }]}>
								{editing ? name || " " : (persona?.name ?? "")}
							</Text>
							{(editing ? status : (persona?.status ?? "")) !== "" && (
								<Text style={[typography.body, { color: colors.mutedForeground, marginTop: 4 }]}>
									{editing ? status : persona?.status}
								</Text>
							)}
						</View>

						{editing ? (
							<>
								<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
									Name
								</Text>
								<TextInput
									style={inputStyle}
									value={name}
									onChangeText={setName}
									placeholder="Name your assistant"
									placeholderTextColor={colors.mutedForeground}
									maxLength={32}
									autoCapitalize="words"
								/>
								<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
									Avatar emoji
								</Text>
								<TextInput
									style={inputStyle}
									value={emoji}
									onChangeText={setEmoji}
									placeholder="\u{1F311}"
									placeholderTextColor={colors.mutedForeground}
									maxLength={8}
								/>
								<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
									Status
								</Text>
								<TextInput
									style={inputStyle}
									value={status}
									onChangeText={setStatus}
									placeholder="e.g. Running audit"
									placeholderTextColor={colors.mutedForeground}
									maxLength={120}
								/>
								<Text style={[styles.label, typography.uiLabel, { color: colors.foreground }]}>
									Vibe
								</Text>
								<TextInput
									style={[inputStyle, styles.multiline]}
									value={vibe}
									onChangeText={setVibe}
									placeholder="How your assistant talks and thinks, e.g. sharp, warm, proactive, technically deep"
									placeholderTextColor={colors.mutedForeground}
									multiline
									maxLength={500}
								/>
								{error ? (
									<Text style={[typography.body, { color: colors.destructive, marginTop: Spacing.sm }]}>
										{error}
									</Text>
								) : null}
								<View style={styles.editRow}>
									<Pressable
										onPress={handleCancel}
										style={({ pressed }) => [
											styles.halfButton,
											{
												backgroundColor: colors.card,
												borderColor: colors.border,
												borderWidth: StyleSheet.hairlineWidth,
												opacity: pressed ? 0.7 : 1,
											},
										]}
										accessibilityRole="button"
										accessibilityLabel="Cancel editing"
									>
										<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
											Cancel
										</Text>
									</Pressable>
									<Pressable
										onPress={() => void handleSave()}
										disabled={saving}
										style={({ pressed }) => [
											styles.halfButton,
											{
												backgroundColor: colors.primary,
												opacity: pressed || saving ? 0.7 : 1,
											},
										]}
										accessibilityRole="button"
										accessibilityLabel="Save assistant identity"
									>
										<Text
											style={[
												typography.uiLabel,
												{ color: colors.primaryForeground, fontWeight: "700" },
											]}
										>
											{saving ? "Saving" : "Save"}
										</Text>
									</Pressable>
								</View>
							</>
						) : (
							<>
								<View
									style={[
										styles.card,
										{
											backgroundColor: colors.card,
											borderColor: colors.border,
										},
									]}
								>
									<View style={styles.cardHeader}>
										<Text style={[typography.uiLabel, { color: colors.foreground, fontWeight: "700" }]}>
											SOUL
										</Text>
										<Text style={[typography.meta, { color: colors.mutedForeground }]}>
											{persona?.updated_at ? formatDate(persona.updated_at) : ""}
										</Text>
									</View>
									<Text style={[typography.body, { color: colors.mutedForeground, marginTop: Spacing.xs }]}>
										Access with care
									</Text>
									<Text style={[typography.body, { color: colors.foreground, marginTop: Spacing.sm }]}>
										{persona?.vibe || "No vibe set yet. Edit to tell your assistant how to talk and think."}
									</Text>
								</View>
								<Text style={[typography.meta, { color: colors.mutedForeground, marginTop: Spacing.md, textAlign: "center" }]}>
									The vibe becomes your assistant's system prompt. Stored encrypted on the node.
								</Text>
								<Pressable
									onPress={() => {
										setEditing(true);
										void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
									}}
									style={({ pressed }) => [
										styles.saveButton,
										{
											backgroundColor: colors.primary,
											opacity: pressed ? 0.85 : 1,
										},
									]}
									accessibilityRole="button"
									accessibilityLabel="Edit assistant identity"
								>
									<Text
										style={[
											typography.uiLabel,
											{ color: colors.primaryForeground, fontWeight: "700" },
										]}
									>
										Edit
									</Text>
								</Pressable>
							</>
						)}
					</>
				)}
			</View>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	container: {
		flexGrow: 1,
		paddingHorizontal: Spacing.xl,
		paddingTop: Spacing.md,
	},
	center: {
		flexGrow: 1,
		justifyContent: "center",
		alignItems: "center",
		gap: Spacing.md,
		paddingHorizontal: Spacing.xl,
	},
	hero: {
		alignItems: "center",
		marginBottom: Spacing.lg,
	},
	avatarCircle: {
		width: 96,
		height: 96,
		borderRadius: 48,
		borderWidth: StyleSheet.hairlineWidth,
		justifyContent: "center",
		alignItems: "center",
	},
	avatarEmoji: {
		fontSize: 48,
	},
	label: {
		marginTop: Spacing.lg,
		marginBottom: Spacing.sm,
		fontWeight: "700",
	},
	input: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusInput,
		paddingHorizontal: Spacing.md,
		paddingVertical: Spacing.md,
		minHeight: SemanticSpacing.inputHeight,
	},
	multiline: {
		minHeight: 120,
		textAlignVertical: "top",
	},
	card: {
		borderWidth: StyleSheet.hairlineWidth,
		borderRadius: SemanticSpacing.radiusModal,
		padding: Spacing.lg,
	},
	cardHeader: {
		flexDirection: "row",
		justifyContent: "space-between",
		alignItems: "center",
	},
	editRow: {
		flexDirection: "row",
		gap: Spacing.sm,
		marginTop: Spacing.xl,
	},
	halfButton: {
		flex: 1,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
	},
	saveButton: {
		marginTop: Spacing.xl,
		borderRadius: SemanticSpacing.radiusModal,
		minHeight: SemanticSpacing.buttonHeightLg,
		justifyContent: "center",
		alignItems: "center",
		paddingHorizontal: Spacing.xl,
	},
});
