/**
 * Cached rendering of node-generated images (Phase 6).
 *
 * GET /media/{id}/content returns raw image bytes, so each image is
 * downloaded once to the app cache with the HMAC auth headers and then
 * rendered from disk. Shared by the media gallery and inline chat images.
 */

import * as FileSystem from "expo-file-system/legacy";
import { useEffect, useState } from "react";
import {
	ActivityIndicator,
	Image,
	StyleSheet,
	Text,
	View,
	type ImageStyle,
	type StyleProp,
} from "react-native";
import { authedDownloadParams, ShadowApiError } from "@/api/shadow";
import { typography, useTheme } from "@/theme";

const CACHE_SUBDIR = "shadow-media";

async function mediaCacheDir(): Promise<string> {
	const dir = `${FileSystem.cacheDirectory}${CACHE_SUBDIR}`;
	try {
		await FileSystem.makeDirectoryAsync(dir, { intermediates: true });
	} catch {
		// already exists
	}
	return dir;
}

/**
 * Local file URI for a generated image, downloading it once if needed.
 * Returns null while loading; throws on failure.
 */
export async function mediaFileUri(mediaId: string): Promise<string> {
	const dir = await mediaCacheDir();
	const dest = `${dir}/${encodeURIComponent(mediaId)}`;
	const info = await FileSystem.getInfoAsync(dest);
	if (info.exists) return dest;
	const { url, headers } = await authedDownloadParams(
		`/media/${encodeURIComponent(mediaId)}/content`,
	);
	const result = await FileSystem.downloadAsync(url, dest, { headers });
	if (result.status !== 200) {
		await FileSystem.deleteAsync(dest, { idempotent: true });
		throw new ShadowApiError(
			result.status === 404 ? "Image not found." : `Image download failed (${result.status}).`,
			result.status,
		);
	}
	return result.uri;
}

/** Hook form of mediaFileUri with loading/error state. */
export function useMediaFileUri(mediaId: string): {
	uri: string | null;
	error: string | null;
} {
	const [uri, setUri] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let cancelled = false;
		setUri(null);
		setError(null);
		mediaFileUri(mediaId)
			.then((u) => {
				if (!cancelled) setUri(u);
			})
			.catch((e: unknown) => {
				if (!cancelled) {
					setError(
						e instanceof ShadowApiError ? e.message : "Could not load the image.",
					);
				}
			});
		return () => {
			cancelled = true;
		};
	}, [mediaId]);

	return { uri, error };
}

export function MediaFileImage({
	mediaId,
	style,
	accessibilityLabel,
}: {
	mediaId: string;
	style?: StyleProp<ImageStyle>;
	accessibilityLabel?: string;
}) {
	const { colors } = useTheme();
	const { uri, error } = useMediaFileUri(mediaId);

	if (error) {
		return (
			<View style={[styles.fallback, style, { backgroundColor: colors.muted }]}>
				<Text style={[typography.meta, { color: colors.mutedForeground }]}>
					Image unavailable
				</Text>
			</View>
		);
	}
	if (!uri) {
		return (
			<View style={[styles.fallback, style, { backgroundColor: colors.muted }]}>
				<ActivityIndicator color={colors.primary} accessibilityLabel="Loading image" />
			</View>
		);
	}
	return (
		<Image
			source={{ uri }}
			style={style}
			resizeMode="cover"
			accessibilityLabel={accessibilityLabel ?? "Generated image"}
		/>
	);
}

const styles = StyleSheet.create({
	fallback: {
		alignItems: "center",
		justifyContent: "center",
	},
});
