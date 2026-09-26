import type { Theme } from "./types";

/**
 * Warm Sand Light Theme
 *
 * Chat-first companion theme: warm cream background (#F6F1EA) with a
 * single cobalt accent (#0064E0). Cobalt is reserved for send and
 * primary actions; everything else stays neutral.
 */
export const warmSandLightTheme: Theme = {
	metadata: {
		id: "warm-sand-light",
		name: "Warm Sand Light",
		description: "A warm, sandy paper-like color scheme - light variant",
		author: "OpenChamber",
		version: "1.0.0",
		variant: "light",
		tags: ["light", "warm", "sand", "paper"],
	},

	colors: {
		primary: {
			base: "#0064E0", // Cobalt - reserved for send + primary actions
			hover: "#0053BC",
			active: "#004CA8",
			foreground: "#fdfcf9",
			muted: "#0064E080",
			emphasis: "#0064E0",
		},

		surface: {
			background: "#F6F1EA", // Warm cream
			foreground: "#3d3833", // oklch(0.25 0.02 40) - dark warm text
			muted: "#ECE7DB", // Light warm gray for hairlines/fills
			mutedForeground: "#6d6860", // oklch(0.45 0.02 50) - medium warm
			elevated: "#FFFFFF", // Cards and popovers
			elevatedForeground: "#3d3833",
			overlay: "#3d383320",
			subtle: "#ECE7DB",
		},

		interactive: {
			border: "#E2DCCF", // Warm hairline
			borderHover: "#d4cfc4",
			borderFocus: "#0064E0",
			selection: "#3d383344",
			selectionForeground: "#3d3833",
			focus: "#0064E0",
			focusRing: "#0064E040",
			cursor: "#3d3833",
			hover: "#ECE7DB",
			active: "#E2DCCF",
		},

		status: {
			error: "#b23e2e", // darkened for WCAG AA (5.16:1 on warm cream)
			errorForeground: "#fdfcf9",
			errorBackground: "#b23e2e20",
			errorBorder: "#b23e2e50",

			warning: "#a05c1a", // darkened for WCAG AA (4.63:1 on warm cream)
			warningForeground: "#fdfcf9",
			warningBackground: "#a05c1a20",
			warningBorder: "#a05c1a50",

			success: "#4a7329", // darkened for WCAG AA (4.95:1 on warm cream)
			successForeground: "#fdfcf9",
			successBackground: "#4a732920",
			successBorder: "#4a732950",

			info: "#346f9f", // darkened for WCAG AA (4.77:1 on warm cream)
			infoForeground: "#fdfcf9",
			infoBackground: "#346f9f20",
			infoBorder: "#346f9f50",
		},

		syntax: {
			base: {
				background: "#e8e5dd",
				foreground: "#3d3833",
				comment: "#8a857c",
				keyword: "#3a7ab8", // Warm blue
				string: "#2a7a6d",
				number: "#8b6bc0",
				function: "#c46c25", // Warm orange
				variable: "#3d3833",
				type: "#a88520", // Golden
				operator: "#c54a3a", // Warm red
			},

			tokens: {
				commentDoc: "#a5a099",
				stringEscape: "#3d3833",
				keywordImport: "#c54a3a",
				storageModifier: "#3a7ab8",
				functionCall: "#c46c25",
				method: "#5a8a35",
				variableProperty: "#3a7ab8",
				variableOther: "#5a8a35",
				variableGlobal: "#a04a70",
				variableLocal: "#fdfcf9",
				parameter: "#3d3833",
				constant: "#3d3833",
				class: "#c46c25",
				className: "#c46c25",
				interface: "#a88520",
				struct: "#c46c25",
				enum: "#c46c25",
				typeParameter: "#c46c25",
				namespace: "#a88520",
				module: "#c54a3a",
				tag: "#3a7ab8",
				jsxTag: "#a04a70",
				tagAttribute: "#a88520",
				tagAttributeValue: "#2a7a6d",
				boolean: "#a88520",
				decorator: "#a88520",
				label: "#a04a70",
				punctuation: "#8a857c",
				macro: "#3a7ab8",
				preprocessor: "#a04a70",
				regex: "#2a7a6d",
				url: "#3a7ab8",
				key: "#c46c25",
				exception: "#a04a70",
			},

			highlights: {
				diffAdded: "#5a8a35",
				diffAddedBackground: "#5a8a3520",
				diffRemoved: "#c54a3a",
				diffRemovedBackground: "#c54a3a20",
				diffModified: "#3a7ab8",
				diffModifiedBackground: "#3a7ab820",
				lineNumber: "#c5c0b6",
				lineNumberActive: "#3d3833",
			},
		},

		markdown: {
			heading1: "#a88520", // Golden
			heading2: "#c46c25", // Warm orange
			heading3: "#3a7ab8", // Warm blue
			heading4: "#3d3833",
			link: "#3a7ab8",
			linkHover: "#4a8ac8",
			inlineCode: "#2a7a6d",
			inlineCodeBackground: "#e8e5dd",
			blockquote: "#6d6860",
			blockquoteBorder: "#d4cfc4",
			listMarker: "#a8852099",
		},

		chat: {
			userMessage: "#232838",
			userMessageBackground: "#E3E9FA", // Pale periwinkle bubble
			assistantMessage: "#3d3833",
			assistantMessageBackground: "#F6F1EA",
			timestamp: "#8a857c",
			divider: "#E2DCCF",
		},

		tools: {
			background: "#e8e5dd50",
			border: "#d4cfc480",
			headerHover: "#d4cfc450",
			icon: "#6d6860",
			title: "#3d3833",
			description: "#6d6860",

			edit: {
				added: "#5a8a35",
				addedBackground: "#5a8a3525",
				removed: "#c54a3a",
				removedBackground: "#c54a3a25",
				lineNumber: "#c5c0b6",
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
