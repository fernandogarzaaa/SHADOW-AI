import Constants from "expo-constants";
import { StyleSheet, Text, View } from "react-native";
import { AgentMark } from "@/components/companion/AgentMark";
import { SettingsGroup, SettingsRow, SettingsScreen } from "@/components/settings/primitives";
import { Spacing, typography, useTheme } from "@/theme";

/**
 * About: what SHADOW is, who makes it, and the license. All statements
 * here are facts about the product, not marketing claims.
 */
export default function AboutScreen() {
	const { colors } = useTheme();

	return (
		<SettingsScreen title="About" showClose={false}>
			<View style={styles.hero}>
				<AgentMark size={72} />
				<Text
					style={[typography.h1, { color: colors.foreground, marginTop: Spacing.sm }]}
				>
					SHADOW
				</Text>
				<Text
					style={[
						typography.body,
						{ color: colors.mutedForeground, textAlign: "center", marginTop: 4 },
					]}
				>
					A personal AI that lives on your phone. Bring your own key,
					chat with a frontier model, and optionally link your own node.
				</Text>
			</View>

			<SettingsGroup>
				<SettingsRow
					title="Version"
					value={Constants.expoConfig?.version ?? "1.0.0"}
				/>
				<SettingsRow title="Built by" value="Fernando Garza" />
				<SettingsRow title="License" value="Apache 2.0" />
			</SettingsGroup>
		</SettingsScreen>
	);
}

const styles = StyleSheet.create({
	hero: {
		alignItems: "center",
		marginBottom: Spacing.lg,
	},
});
