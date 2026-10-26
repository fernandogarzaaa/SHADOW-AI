import type { BrowserStep, BrowserTaskStatus } from "@/api/shadow";

/** Plain-language task status. Pure (unit-testable without Expo). */
export function browserStatusLabel(status: BrowserTaskStatus | string): string {
	switch (status) {
		case "queued":
			return "Starting";
		case "running":
			return "Working";
		case "waiting_approval":
			return "Needs your approval";
		case "waiting_user":
			return "Has a question";
		case "done":
			return "Done";
		case "failed":
			return "Failed";
		case "stopped":
			return "Stopped";
		default:
			return status;
	}
}

/** One-line description of a step the model took. Pure. */
export function describeBrowserStep(a: BrowserStep["action"]): string {
	switch (a.action) {
		case "go":
			return `Open ${a.url ?? ""}`;
		case "click":
			return `Click element ${a.index ?? "?"}`;
		case "type":
			return `Type "${a.text ?? ""}"${a.submit ? " and submit" : ""}`;
		case "select":
			return `Choose "${a.value ?? ""}"`;
		case "scroll":
			return `Scroll ${a.direction ?? "down"}`;
		case "back":
			return "Go back";
		case "note":
			return `Note: ${a.text ?? ""}`;
		case "ask":
			return `Ask you: ${a.text ?? ""}`;
		case "done":
			return "Finish";
		default:
			return a.action;
	}
}
