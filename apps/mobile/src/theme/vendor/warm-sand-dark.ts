import type { Theme } from "./types";

/**
 * Warm Sand Dark Theme
 *
 * SHADOW deep-ink dark variant: a warm near-black background with warm
 * neutral surfaces and a single cobalt accent (#0064E0), matching the
 * light theme's reserved cobalt for send and primary actions.
 */
export const warmSandDarkTheme: Theme = {
	metadata: {
		id: "warm-sand-dark",
		name: "Warm Sand Dark",
		description: "A deep-ink, warm-neutral dark scheme with a cobalt accent",
		author: "OpenChamber",
		version: "1.0.0",
		variant: "dark",
		tags: ["dark", "warm", "ink", "cobalt"],
	},

	colors: {
		primary: {
			base: "#2f7fe8", // Cobalt lightened for dark surfaces (4.66:1 on deep ink)
			hover: "#4b92ec",
			active: "#1f6cd6",
			foreground: "#161412", // deep ink on cobalt: 4.66:1, passes AA
			muted: "#2f7fe880",
			emphasis: "#4b92ec",
		},

		surface: {
			background: "#161412", // deep ink, warm undertone
			foreground: "#e9e2d5", // warm off-white
			muted: "#292521", // warm neutral fill
			mutedForeground: "#a9a091", // warm gray text (AA on deep ink)
			elevated: "#1e1b17",
			elevatedForeground: "#e9e2d5",
			overlay: "#00000080",
			subtle: "#232019",
		},

		interactive: {
			border: "#2e2924", // hairline on deep ink
			borderHover: "#3d3730",
			borderFocus: "#2f7fe8", // cobalt
			selection: "#e9e2d530",
			selectionForeground: "#e9e2d5",
			focus: "#2f7fe8", // cobalt
			focusRing: "#2f7fe850", // cobalt
			cursor: "#e9e2d5",
			hover: "#232019",
			active: "#292521",
		},

		status: {
			error: "#e08a7a", // warm red, lightened for dark
			errorForeground: "#161412",
			errorBackground: "#e08a7a20",
			errorBorder: "#e08a7a50",

			warning: "#e8b93e",
			warningForeground: "#161412",
			warningBackground: "#e8b93e20",
			warningBorder: "#e8b93e50",

			success: "#8fbf7d", // warm green, lightened for dark
			successForeground: "#161412",
			successBackground: "#8fbf7d20",
			successBorder: "#8fbf7d50",

			info: "#6fb3e0", // soft blue, lightened for dark
			infoForeground: "#161412",
			infoBackground: "#6fb3e020",
			infoBorder: "#6fb3e050",
		},

		syntax: {
			base: {
				background: "#1e1b17",
				foreground: "#e9e2d5",
				comment: "#7a7264",
				keyword: "#6fb3e0", // Soft blue
				string: "#7fbfe0",
				number: "#d8a17e",
				function: "#d8a17e",
				variable: "#e9e2d5",
				type: "#c9a45c", // Warm sand
				operator: "#e08a7a", // Warm red
			},

			tokens: {
				commentDoc: "#655d52",
				stringEscape: "#e9e2d5",
				keywordImport: "#e08a7a",
				storageModifier: "#6fb3e0",
				functionCall: "#d8a17e",
				method: "#8fbf7d",
				variableProperty: "#6fb3e0",
				variableOther: "#8fbf7d",
				variableGlobal: "#d47ba3",
				variableLocal: "#2a2621",
				parameter: "#e9e2d5",
				constant: "#e9e2d5",
				class: "#d8a17e",
				className: "#d8a17e",
				interface: "#c9a45c",
				struct: "#d8a17e",
				enum: "#d8a17e",
				typeParameter: "#d8a17e",
				namespace: "#c9a45c",
				module: "#e08a7a",
				tag: "#6fb3e0",
				jsxTag: "#d47ba3",
				tagAttribute: "#c9a45c",
				tagAttributeValue: "#7fbfe0",
				boolean: "#c9a45c",
				decorator: "#c9a45c",
				label: "#d47ba3",
				punctuation: "#7a7264",
				macro: "#6fb3e0",
				preprocessor: "#d47ba3",
				regex: "#7fbfe0",
				url: "#6fb3e0",
				key: "#d8a17e",
				exception: "#d47ba3",
			},

			highlights: {
				diffAdded: "#8fbf7d",
				diffAddedBackground: "#8fbf7d20",
				diffRemoved: "#e08a7a",
				diffRemovedBackground: "#e08a7a20",
				diffModified: "#6fb3e0",
				diffModifiedBackground: "#6fb3e020",
				lineNumber: "#2e2924",
				lineNumberActive: "#e9e2d5",
			},
		},

		markdown: {
			heading1: "#c9a45c", // Warm sand
			heading2: "#d8a17e", // Warm clay
			heading3: "#6fb3e0", // Soft blue
			heading4: "#e9e2d5",
			link: "#6fb3e0",
			linkHover: "#7fbfe0",
			inlineCode: "#8fbf7d",
			inlineCodeBackground: "#1e1b17",
			blockquote: "#a9a091",
			blockquoteBorder: "#2e2924",
			listMarker: "#c9a45c99",
		},

		chat: {
			userMessage: "#e9e2d5",
			userMessageBackground: "#2a2621",
			assistantMessage: "#e9e2d5",
			assistantMessageBackground: "#161412",
			timestamp: "#7a7264",
			divider: "#2e2924",
		},

		tools: {
			background: "#1e1b1750",
			border: "#2e292480",
			headerHover: "#2e292450",
			icon: "#a9a091",
			title: "#e9e2d5",
			description: "#a9a091",

			edit: {
				added: "#8fbf7d",
				addedBackground: "#8fbf7d25",
				removed: "#e08a7a",
				removedBackground: "#e08a7a25",
				lineNumber: "#2e2924",
			},
		},
	},

	config: {
		fonts: {
			sans: '"IBM Plex Mono", monospace',
			mono: '"IBM Plex Mono", monospace',
			heading: '"IBM Plex Mono", monospace',
		},

		radius: {
			none: "0",
			sm: "0.125rem",
			md: "0.375rem",
			lg: "0.5rem",
			xl: "0.75rem",
			full: "9999px",
		},

		transitions: {
			fast: "150ms ease",
			normal: "250ms ease",
			slow: "350ms ease",
		},
	},
};
