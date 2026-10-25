import { useEffect, useMemo, useState } from "react";
import { AppState } from "react-native";
import Svg, { Circle, Line } from "react-native-svg";
import { MODE_FRAMES, resolvePreset } from "thinking-orbs/engine";
import { useReduceMotion } from "@/hooks/useReduceMotion";
import { useTheme } from "@/theme";

/**
 * Dotted "thought orb" from thinking-orbs (libraries.dev, MIT).
 *
 * Geometry comes from the package's React-free engine: the same frame
 * functions the node's web dashboard runs, so both clients animate
 * identically. Frames are drawn with react-native-svg (already a
 * dependency) instead of the upstream Skia port, so no new native module
 * is needed. Colours mirror the engine's `inkColor` painter.
 */
export type OrbState =
	| "working"
	| "searching"
	| "solving"
	| "listening"
	| "connecting"
	| "weaving"
	| "composing"
	| "breathing"
	| "shaping";

interface ThinkingOrbProps {
	state?: OrbState;
	/** Tuned presets: 20 (inline), 32 (compact), 64 (avatar). */
	size?: 20 | 32 | 64;
	paused?: boolean;
	accessibilityLabel?: string;
}

/** Same instant the web component shows under reduced motion. */
const STATIC_T = 0.6;
/** Small indicators read smoothly at 30 fps and halve the JS work. */
const FRAME_MS = 1000 / 30;

function ink(white: number, alpha: number, dark: boolean): string {
	const w = Math.min(1, Math.max(0, white));
	const g = Math.round((dark ? 1 - w : w) * 255);
	return `rgba(${g},${g},${g},${alpha})`;
}

export function ThinkingOrb({
	state = "working",
	size = 20,
	paused = false,
	accessibilityLabel,
}: ThinkingOrbProps) {
	const { isDark } = useTheme();
	const reduceMotion = useReduceMotion();
	const [t, setT] = useState(STATIC_T);
	const [appActive, setAppActive] = useState(AppState.currentState === "active");

	const { frameFn, speed, opts } = useMemo(() => {
		const resolved = resolvePreset(state, size);
		return { frameFn: MODE_FRAMES[resolved.mode], speed: resolved.speed, opts: resolved.opts };
	}, [state, size]);

	useEffect(() => {
		const sub = AppState.addEventListener("change", (s) => setAppActive(s === "active"));
		return () => sub.remove();
	}, []);

	useEffect(() => {
		if (paused || reduceMotion || !appActive) return;
		let raf = 0;
		let last = 0;
		const loop = (now: number) => {
			if (now - last >= FRAME_MS) {
				last = now;
				setT(Date.now() / 1000);
			}
			raf = requestAnimationFrame(loop);
		};
		raf = requestAnimationFrame(loop);
		return () => cancelAnimationFrame(raf);
	}, [paused, reduceMotion, appActive]);

	const frame = frameFn(size, (reduceMotion ? STATIC_T : t) * speed, opts);

	return (
		<Svg
			width={size}
			height={size}
			accessibilityRole="image"
			accessibilityLabel={accessibilityLabel ?? state}
		>
			{frame.lines.map((l, i) => (
				<Line
					key={`l${i}`}
					x1={l.x1}
					y1={l.y1}
					x2={l.x2}
					y2={l.y2}
					stroke={ink(l.white, l.a ?? 1, isDark)}
					strokeWidth={l.w}
				/>
			))}
			{frame.dots.map((d, i) => (
				<Circle key={i} cx={d.x} cy={d.y} r={d.r} fill={ink(d.white, d.a ?? 1, isDark)} />
			))}
		</Svg>
	);
}
