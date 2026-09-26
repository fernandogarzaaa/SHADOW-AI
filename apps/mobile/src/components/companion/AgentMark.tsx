import Svg, { Path } from "react-native-svg";
import { useTheme } from "@/theme";

/**
 * The agent mark: a soft beige blob with a small hand-drawn sparkle.
 * Used for the wordmark moments (onboarding, empty state). Deliberately
 * not a robot icon.
 */
export function AgentMark({ size = 72 }: { size?: number }) {
	const { colors } = useTheme();

	return (
		<Svg width={size} height={size} viewBox="0 0 120 120">
			<Path
				d="M60 8 C88 6 110 26 112 54 C114 84 96 108 64 110 C32 112 10 92 9 62 C8 32 34 10 60 8 Z"
				fill={colors.blob}
			/>
			<Path
				d="M60 34 C62 46 64 54 66 66"
				stroke={colors.foreground}
				strokeWidth={5}
				strokeLinecap="round"
				fill="none"
			/>
			<Path
				d="M38 58 C50 58 70 58 84 57"
				stroke={colors.foreground}
				strokeWidth={5}
				strokeLinecap="round"
				fill="none"
			/>
			<Path
				d="M46 44 C54 52 66 64 74 72"
				stroke={colors.foreground}
				strokeWidth={5}
				strokeLinecap="round"
				fill="none"
			/>
			<Path
				d="M74 44 C66 52 54 64 46 72"
				stroke={colors.foreground}
				strokeWidth={5}
				strokeLinecap="round"
				fill="none"
			/>
		</Svg>
	);
}
