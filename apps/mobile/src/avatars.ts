/**
 * Shadow agent avatars: five abstract icons in warm cream, cobalt, and
 * ink. No faces, no text. Bundled as PNGs under assets/images/avatars so
 * they render offline and in EAS builds. Metro requires static require()
 * calls, so each avatar is listed explicitly in the manifest below.
 */

export type AvatarId = "eclipse" | "rings" | "wisp" | "diamond" | "crescent";

export interface AvatarDef {
	id: AvatarId;
	/** Short human label, used for accessibility and the picker. */
	label: string;
	source: { uri?: string } | number;
}

const BY_ID: Record<AvatarId, AvatarDef> = {
	eclipse: {
		id: "eclipse",
		label: "Eclipse",
		source: require("../assets/images/avatars/avatar-eclipse.png"),
	},
	rings: {
		id: "rings",
		label: "Rings",
		source: require("../assets/images/avatars/avatar-rings.png"),
	},
	wisp: {
		id: "wisp",
		label: "Wisp",
		source: require("../assets/images/avatars/avatar-wisp.png"),
	},
	diamond: {
		id: "diamond",
		label: "Diamond",
		source: require("../assets/images/avatars/avatar-diamond.png"),
	},
	crescent: {
		id: "crescent",
		label: "Crescent",
		source: require("../assets/images/avatars/avatar-crescent.png"),
	},
};

export const AVATARS: readonly AvatarDef[] = [
	BY_ID.eclipse,
	BY_ID.rings,
	BY_ID.wisp,
	BY_ID.diamond,
	BY_ID.crescent,
];

export const DEFAULT_AVATAR_ID: AvatarId = "eclipse";

/** True for the five known avatar ids, false for anything else. */
export function isAvatarId(value: unknown): value is AvatarId {
	return (
		typeof value === "string" &&
		(value === "eclipse" ||
			value === "rings" ||
			value === "wisp" ||
			value === "diamond" ||
			value === "crescent")
	);
}

/**
 * Resolve any stored value to a valid avatar id. Unknown, missing, or
 * corrupt values fall back to the default instead of crashing.
 */
export function resolveAvatarId(value: unknown): AvatarId {
	return isAvatarId(value) ? value : DEFAULT_AVATAR_ID;
}

/** Get the full avatar definition for any value, never throws. */
export function getAvatar(id: unknown): AvatarDef {
	return BY_ID[resolveAvatarId(id)];
}
