/**
 * Local profile (memory v1).
 *
 * Explicit facts only: things the user typed themselves. SHADOW does not
 * learn in the background and does not consolidate across threads. The
 * profile is injected into the provider system prompt verbatim, and the
 * settings copy says exactly what it does.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";
import { create } from "zustand";
import {
	DEFAULT_AVATAR_ID,
	isAvatarId,
	type AvatarId,
} from "@/avatars";

const STORAGE_KEY = "shadow.profile.v1";

export type AgentTone = "warm" | "direct" | "playful";

export interface UserProfile {
	/** Display name the assistant should use. */
	name: string;
	/** Free-form facts, one per line in the editor. */
	facts: string[];
	/** Communication preferences, e.g. "Keep answers short." */
	preferences: string[];
	/** What the user named their agent. Defaults to "shadow". */
	agentName: string;
	/** How the agent should talk. */
	tone: AgentTone;
	/** Which shadow avatar is the agent's face. Defaults to "eclipse". */
	avatarId: AvatarId;
	updatedAt: number;
}

const EMPTY_PROFILE: UserProfile = {
	name: "",
	facts: [],
	preferences: [],
	agentName: "shadow",
	tone: "warm",
	avatarId: DEFAULT_AVATAR_ID,
	updatedAt: 0,
};

interface ProfileStoreState {
	profile: UserProfile;
	initialized: boolean;
	initialize: () => Promise<void>;
	saveProfile: (patch: Partial<Omit<UserProfile, "updatedAt">>) => Promise<void>;
	clearProfile: () => Promise<void>;
}

async function persist(profile: UserProfile): Promise<void> {
	try {
		await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
	} catch {
		// best-effort
	}
}

export const useProfileStore = create<ProfileStoreState>()((set) => ({
	profile: EMPTY_PROFILE,
	initialized: false,

	initialize: async () => {
		try {
			const raw = await AsyncStorage.getItem(STORAGE_KEY);
			if (raw) {
				const parsed = JSON.parse(raw) as UserProfile;
				set({
					profile: {
						name: typeof parsed.name === "string" ? parsed.name : "",
						facts: Array.isArray(parsed.facts) ? parsed.facts.filter((f) => typeof f === "string") : [],
						preferences: Array.isArray(parsed.preferences) ? parsed.preferences.filter((p) => typeof p === "string") : [],
						agentName: typeof parsed.agentName === "string" && parsed.agentName.trim() ? parsed.agentName.trim() : "shadow",
						tone: parsed.tone === "direct" || parsed.tone === "playful" ? parsed.tone : "warm",
						avatarId: isAvatarId(parsed.avatarId) ? parsed.avatarId : DEFAULT_AVATAR_ID,
						updatedAt: typeof parsed.updatedAt === "number" ? parsed.updatedAt : 0,
					},
					initialized: true,
				});
				return;
			}
		} catch {
			// fall through to empty profile
		}
		set({ profile: EMPTY_PROFILE, initialized: true });
	},

	saveProfile: async (patch) => {
		const prev = useProfileStore.getState().profile;
		const profile: UserProfile = {
			name: (patch.name ?? prev.name).trim(),
			facts: (patch.facts ?? prev.facts).map((f) => f.trim()).filter((f) => f.length > 0),
			preferences: (patch.preferences ?? prev.preferences).map((p) => p.trim()).filter((p) => p.length > 0),
			agentName: (patch.agentName ?? prev.agentName).trim() || "shadow",
			tone: patch.tone ?? prev.tone,
			avatarId:
				patch.avatarId && isAvatarId(patch.avatarId)
					? patch.avatarId
					: prev.avatarId,
			updatedAt: Date.now(),
		};
		set({ profile });
		await persist(profile);
	},

	clearProfile: async () => {
		set({ profile: { ...EMPTY_PROFILE } });
		await persist({ ...EMPTY_PROFILE });
	},
}));

/**
 * Build the system prompt prefix from an explicit local profile.
 * Pure: unit-testable. Returns "" when the profile is empty.
 */
export function buildProfilePrompt(profile: UserProfile): string {
	const lines: string[] = [];
	if (profile.name) {
		lines.push(`The user's name is ${profile.name}.`);
	}
	for (const fact of profile.facts) {
		lines.push(`About the user: ${fact}`);
	}
	for (const pref of profile.preferences) {
		lines.push(`Preference: ${pref}`);
	}
	if (lines.length === 0) {
		return "";
	}
	return [
		"Facts the user explicitly told you about themselves. Use them naturally; do not claim to have learned anything beyond these.",
		...lines,
	].join("\n");
}
