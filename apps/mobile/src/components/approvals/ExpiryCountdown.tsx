import { useEffect, useState } from "react";
import { Text } from "react-native";

interface ExpiryCountdownProps {
	/** ISO-8601 timestamp at which the approval expires. */
	expiresAt: string;
	className?: string;
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
export function ExpiryCountdown({ expiresAt, className }: ExpiryCountdownProps) {
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
			className={`text-xs ${isExpired ? "text-red-400" : isUrgent ? "text-amber-400" : "text-white/50"} ${className ?? ""}`}
		>
			{formatRemaining(remaining)}
		</Text>
	);
}
