import { useEffect, useState } from "react";
import { Text, type TextStyle } from "react-native";
import { typography, useTheme } from "@/theme";

interface ExpiryCountdownProps {
	/** ISO-8601 timestamp at which the approval expires. */
	expiresAt: string;
	style?: TextStyle;
}

function formatRemaining(ms: number): string {
	if (ms <= 0) {
		return "Expired";
	}
	const totalSeconds = Math.floor(ms / 1000);
	const minutes = Math.floor(totalSeconds / 60);
	const seconds = totalSeconds % 60;
	if (minutes <= 0) {
		return `Expires in ${seconds}s`;
	}
	if (minutes < 60) {
		return `Expires in ${minutes}m ${seconds}s`;
	}
	const hours = Math.floor(minutes / 60);
	return `Expires in ${hours}h ${minutes % 60}m`;
}

/** Live-updating relative expiry text for an approval request. */
export function ExpiryCountdown({ expiresAt, style }: ExpiryCountdownProps) {
	const { colors } = useTheme();
	const [now, setNow] = useState(() => Date.now());

	useEffect(() => {
		const interval = setInterval(() => {
			setNow(Date.now());
		}, 1000);
		return () => clearInterval(interval);
	}, [expiresAt]);

	const expires = Date.parse(expiresAt);
	if (Number.isNaN(expires)) {
		return null;
	}

	const remaining = expires - now;
	const isExpired = remaining <= 0;
	const isUrgent = !isExpired && remaining < 60_000;

	return (
		<Text
			style={[
				typography.meta,
				{
					color: isExpired
						? colors.destructive
						: isUrgent
							? colors.warning
							: colors.mutedForeground,
				},
				style,
			]}
		>
			{formatRemaining(remaining)}
		</Text>
	);
}
