import {
	Image,
	StyleSheet,
	type ImageStyle,
	type StyleProp,
} from "react-native";
import { getAvatar, type AvatarId } from "@/avatars";

interface ShadowAvatarProps {
	/** Any stored value is safe: unknown ids fall back to the default avatar. */
	avatarId: AvatarId | string | null | undefined;
	/** Diameter in points. */
	size?: number;
	style?: StyleProp<ImageStyle>;
	testID?: string;
}

/**
 * The agent's face: a circular crop of the chosen shadow avatar.
 * The source art is warm cream, cobalt, and ink with no faces or text.
 */
export function ShadowAvatar({
	avatarId,
	size = 40,
	style,
	testID,
}: ShadowAvatarProps) {
	const avatar = getAvatar(avatarId);
	return (
		<Image
			source={avatar.source}
			testID={testID}
			style={[
				styles.image,
				{ width: size, height: size, borderRadius: size / 2 },
				style,
			]}
			accessibilityRole="image"
			accessibilityLabel={`${avatar.label} avatar`}
		/>
	);
}

const styles = StyleSheet.create({
	image: {
		resizeMode: "cover",
	},
});
