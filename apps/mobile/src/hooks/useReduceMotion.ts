import { useEffect, useState } from "react";
import { AccessibilityInfo } from "react-native";

/**
 * True when the OS requests reduced motion. Pulse loops, shimmer, and
 * other decorative animation should render a static frame instead.
 * State is always paired with a text label, never conveyed by motion
 * or color alone.
 */
export function useReduceMotion(): boolean {
	const [reduceMotion, setReduceMotion] = useState(false);

	useEffect(() => {
		let mounted = true;
		AccessibilityInfo.isReduceMotionEnabled()
			.then((enabled) => {
				if (mounted) setReduceMotion(enabled ?? false);
			})
			.catch(() => {
				// best-effort: assume full motion when the API is unavailable
			});
		const subscription = AccessibilityInfo.addEventListener(
			"reduceMotionChanged",
			setReduceMotion,
		);
		return () => {
			mounted = false;
			subscription.remove();
		};
	}, []);

	return reduceMotion;
}
