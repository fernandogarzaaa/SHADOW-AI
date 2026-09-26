import * as Haptics from "expo-haptics";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import {
	ActivityIndicator,
	RefreshControl,
	ScrollView,
	StyleSheet,
	Text,
	View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { AvatarStatusPill } from "@/components/AvatarStatusPill";
import { ClaimCard } from "@/components/briefing/ClaimCard";
import {
	type AmbientRun,
	type AmbientStatus,
	type Claim,
	type ExecutionSummary,
	getAmbientStatus,
	listAmbientRuns,
	listClaims,
	listExecutions,
} from "@/api/shadow";
import { useProviderChat } from "@/hooks/useProviderChat";
import { useReduceMotion } from "@/hooks/useReduceMotion";
import { useConnectionStore } from "@/stores/useConnectionStore";
import { useProfileStore } from "@/stores/useProfileStore";
import { SemanticSpacing, Spacing, typography, useTheme } from "@/theme";
import { Badge, Button, DepthBackground, GlassView } from "@/components/ui";

function greetingFor(date: Date): string {
	const day = date.toLocaleDateString(undefined, { weekday: "long" });
	const hour = date.getHours();
	const part =
		hour < 5 ? "night" : hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
	return `${day} ${part}`;
}

function verdictColor(verdict: string | undefined, colors: { success: string; destructive: string; warning: string; mutedForeground: string }) {
	switch (verdict) {
		case "VERIFIED":
			return colors.success;
		case "FAILED":
			return colors.destructive;
		case "UNCERTAIN":
		case "CONFLICTING":
			return colors.warning;
		default:
			return colors.mutedForeground;
	}
}

function timeAgo(iso: string | undefined): string {
	if (!iso) return "";
	const ms = Date.now() - new Date(iso).getTime();
	if (Number.isNaN(ms)) return "";
	const minutes = Math.floor(ms / 60000);
	if (minutes < 1) return "just now";
	if (minutes < 60) return `${minutes}m ago`;
	const hours = Math.floor(minutes / 60);
	if (hours < 24) return `${hours}h ago`;
	return `${Math.floor(hours / 24)}d ago`;
}

interface BriefingData {
	status: AmbientStatus;
	runs: AmbientRun[];
	executions: ExecutionSummary[];
	claims: Claim[];
}

function useBriefingData(isPaired: boolean) {
	const [data, setData] = useState<BriefingData | null>(null);
	const [loading, setLoading] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const load = useCallback(async () => {
		if (!isPaired) return;
		setLoading(true);
		setError(null);
		try {
			const [status, runs, executions, claims] = await Promise.all([
				getAmbientStatus(),
				listAmbientRuns(10),
				listExecutions(10),
				listClaims("unconfirmed"),
			]);
			setData({ status, runs, executions, claims });
		} catch (e) {
			setError(
				e instanceof Error ? e.message : "Could not reach the node.",
			);
		} finally {
			setLoading(false);
		}
	}, [isPaired]);

	useFocusEffect(
		useCallback(() => {
			void load();
		}, [load]),
	);

	return { data, loading, error, reload: load };
}

function SectionCard({
	title,
	count,
	children,
}: {
	title: string;
	count?: number;
	children: React.ReactNode;
}) {
	const { colors } = useTheme();
	return (
		<GlassView borderRadius={SemanticSpacing.radiusCard}>
			<View style={styles.cardInner}>
				<View style={styles.cardHeader}>
					<Text style={[typography.titleSmall, { color: colors.foreground }]}>
						{title}
					</Text>
					{typeof count === "number" ? (
						<Badge variant="secondary">{String(count)}</Badge>
					) : null}
				</View>
				{children}
			</View>
		</GlassView>
	);
}

/**
 * Briefing tab: a calm digest of what the linked SHADOW node has been
 * doing, built only from real ambient surfaces (runs, executions,
 * claims, scheduler status). Nothing is invented; with no node linked
 * the screen says so and points at Settings.
 */
export default function BriefingScreen() {
	const { colors } = useTheme();
	const insets = useSafeAreaInsets();
	const reduceMotion = useReduceMotion();
	const isPaired = useConnectionStore((s) => s.isPaired);
	const agentName = useProfileStore((s) => s.profile.agentName);
	const avatarId = useProfileStore((s) => s.profile.avatarId);
	const { agentState } = useProviderChat();
	const { data, loading, error, reload } = useBriefingData(isPaired);
	const [refreshing, setRefreshing] = useState(false);
	/** Claims the user decided on this session; hidden optimistically. */
	const [resolvedClaimIds, setResolvedClaimIds] = useState<Set<string>>(
		() => new Set(),
	);

	const onRefresh = useCallback(async () => {
		setRefreshing(true);
		Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
		setResolvedClaimIds(new Set());
		await reload();
		setRefreshing(false);
	}, [reload]);

	const handleClaimResolved = useCallback((claimId: string) => {
		setResolvedClaimIds((prev) => {
			const next = new Set(prev);
			next.add(claimId);
			return next;
		});
	}, []);

	const openClaims = (data?.claims ?? []).filter(
		(c) => !resolvedClaimIds.has(c.claim_id),
	);

	const greeting = greetingFor(new Date());
	const ambientOn = data?.status.config?.enabled === true;

	return (
		<View style={styles.container}>
			<DepthBackground />
			<ScrollView
				style={styles.scroll}
				contentContainerStyle={[
					styles.content,
					{ paddingTop: insets.top + Spacing.md, paddingBottom: 120 },
				]}
				refreshControl={
					<RefreshControl
						refreshing={refreshing}
						onRefresh={() => void onRefresh()}
						tintColor={colors.primary}
					/>
				}
			>
				<View style={styles.hero}>
					<AvatarStatusPill
						avatarId={avatarId}
						agentName={agentName || "shadow"}
						state={agentState}
						size={96}
					/>
					<Text
						style={[typography.titleLarge, { color: colors.foreground, textAlign: "center" }]}
						accessibilityRole="header"
					>
						{greeting}
					</Text>
					<Text
						style={[
							typography.body,
							{ color: colors.mutedForeground, textAlign: "center", marginTop: 4 },
						]}
					>
						{isPaired
							? "Here is what your node has been up to."
							: "Link your node to get briefings on what it has been doing."}
					</Text>
				</View>

				{!isPaired ? (
					<GlassView borderRadius={SemanticSpacing.radiusCard}>
						<View style={styles.cardInner}>
							<Text style={[typography.titleSmall, { color: colors.foreground }]}>
								No node linked
							</Text>
							<Text
								style={[
									typography.body,
									{ color: colors.mutedForeground, marginTop: 4 },
								]}
							>
								Briefings come from your SHADOW node: its runs, executions,
								and claims. Link a node to start receiving them.
							</Text>
							<Button
								variant="primary"
								size="md"
								onPress={() => router.push("/settings/link-node")}
								accessibilityLabel="Link a node in settings"
								style={styles.cta}
							>
								Link a node
							</Button>
						</View>
					</GlassView>
				) : loading && !data ? (
					<View style={styles.centered}>
						<ActivityIndicator
							size="large"
							color={colors.primary}
							animating={!reduceMotion}
						/>
						<Text
							style={[
								typography.body,
								{ color: colors.mutedForeground, marginTop: Spacing.sm },
							]}
						>
							Asking your node for the latest...
						</Text>
					</View>
				) : error && !data ? (
					<GlassView borderRadius={SemanticSpacing.radiusCard}>
						<View style={styles.cardInner}>
							<Text style={[typography.titleSmall, { color: colors.foreground }]}>
								Could not reach the node
							</Text>
							<Text
								style={[
									typography.body,
									{ color: colors.mutedForeground, marginTop: 4 },
								]}
							>
								{error}
							</Text>
							<Button
								variant="outline"
								size="md"
								onPress={() => void reload()}
								accessibilityLabel="Try again"
								style={styles.cta}
							>
								Try again
							</Button>
						</View>
					</GlassView>
				) : data ? (
					<>
						<SectionCard title="Node status">
							<View style={styles.kvRow}>
								<Text style={[typography.body, { color: colors.foreground }]}>
									Ambient scheduler
								</Text>
								<Badge variant={ambientOn ? "success" : "secondary"}>
									{ambientOn ? "ON" : "OFF"}
								</Badge>
							</View>
							<View style={styles.kvRow}>
								<Text style={[typography.body, { color: colors.foreground }]}>
									Background work
								</Text>
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									{data.status.background_running ? "running" : "idle"}
								</Text>
							</View>
						</SectionCard>

						<SectionCard title="Recent runs" count={data.runs.length}>
							{data.runs.length === 0 ? (
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									No runs recorded yet.
								</Text>
							) : (
								data.runs.slice(0, 5).map((run) => (
									<View key={run.run_id} style={styles.itemRow}>
										<View style={styles.itemText}>
											<Text
												style={[typography.body, { color: colors.foreground }]}
												numberOfLines={1}
											>
												{run.objective || run.run_id}
											</Text>
											<Text style={[typography.meta, { color: colors.mutedForeground }]}>
												{[run.status, timeAgo(run.started_at)]
													.filter(Boolean)
													.join(" · ")}
											</Text>
										</View>
									</View>
								))
							)}
						</SectionCard>

						<SectionCard title="Recent executions" count={data.executions.length}>
							{data.executions.length === 0 ? (
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									No executions verified yet.
								</Text>
							) : (
								data.executions.slice(0, 5).map((exec) => (
									<View key={exec.execution_id} style={styles.itemRow}>
										<View
											style={[
												styles.dot,
												{
													backgroundColor: verdictColor(exec.verification, colors),
												},
											]}
										/>
										<View style={styles.itemText}>
											<Text
												style={[typography.body, { color: colors.foreground }]}
												numberOfLines={1}
											>
												{exec.intent || exec.tool_name || exec.execution_id}
											</Text>
											<Text style={[typography.meta, { color: colors.mutedForeground }]}>
												{[exec.verification, timeAgo(exec.started_at)]
													.filter(Boolean)
													.join(" · ")}
											</Text>
										</View>
									</View>
								))
							)}
						</SectionCard>

						<SectionCard title="Open claims" count={openClaims.length}>
							{openClaims.length === 0 ? (
								<Text style={[typography.body, { color: colors.mutedForeground }]}>
									Nothing waiting on confirmation.
								</Text>
							) : (
								<View style={styles.claimList}>
									{openClaims.slice(0, 5).map((claim) => (
										<ClaimCard
											key={claim.claim_id}
											claim={claim}
											onResolved={handleClaimResolved}
										/>
									))}
								</View>
							)}
						</SectionCard>
					</>
				) : null}
			</ScrollView>
		</View>
	);
}

const styles = StyleSheet.create({
	container: {
		flex: 1,
	},
	scroll: {
		flex: 1,
	},
	content: {
		paddingHorizontal: Spacing.lg,
		gap: Spacing.md,
	},
	hero: {
		alignItems: "center",
		marginBottom: Spacing.sm,
	},
	cardInner: {
		padding: Spacing.md,
	},
	cardHeader: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		gap: Spacing.sm,
		marginBottom: Spacing.sm,
	},
	centered: {
		alignItems: "center",
		paddingVertical: Spacing.xl,
	},
	cta: {
		marginTop: Spacing.md,
		alignSelf: "flex-start",
	},
	kvRow: {
		flexDirection: "row",
		alignItems: "center",
		justifyContent: "space-between",
		paddingVertical: Spacing.xs,
		minHeight: SemanticSpacing.buttonHeightMd,
	},
	itemRow: {
		flexDirection: "row",
		alignItems: "center",
		gap: Spacing.sm,
		paddingVertical: Spacing.sm,
		minHeight: SemanticSpacing.buttonHeightMd,
	},
	itemText: {
		flex: 1,
		gap: 2,
	},
	dot: {
		width: 8,
		height: 8,
		borderRadius: 4,
	},
	claimList: {
		gap: Spacing.sm,
	},
});
