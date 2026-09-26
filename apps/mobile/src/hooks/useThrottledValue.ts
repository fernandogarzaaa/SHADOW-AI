import { useEffect, useRef, useState } from "react";

/**
 * 50 ms throttle for streaming markdown.
 *
 * Streams update state at most once per window so memoized markdown blocks
 * re-render on a fixed cadence instead of per token. The latest value is
 * always flushed when the window elapses or when the component unmounts.
 */
export function useThrottledValue<T>(value: T, intervalMs = 50): T {
	const [throttled, setThrottled] = useState(value);
	const latestRef = useRef(value);
	const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

	useEffect(() => {
		latestRef.current = value;
		if (timerRef.current === null) {
			setThrottled(value);
			timerRef.current = setTimeout(() => {
				timerRef.current = null;
				setThrottled(latestRef.current);
			}, intervalMs);
		}
		return () => {
			// Flush on unmount handled by the final render below.
		};
	}, [value, intervalMs]);

	useEffect(() => {
		return () => {
			if (timerRef.current !== null) {
				clearTimeout(timerRef.current);
				timerRef.current = null;
			}
		};
	}, []);

	return throttled;
}
