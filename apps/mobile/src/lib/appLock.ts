/**
 * App lock using the device's biometric / passcode authentication.
 * Real expo-local-authentication; no mock.
 */

import * as LocalAuthentication from "expo-local-authentication";

/** True when the device has biometric hardware with at least one enrolled identity. */
export async function deviceSupportsBiometrics(): Promise<boolean> {
	try {
		const [hasHardware, enrolled] = await Promise.all([
			LocalAuthentication.hasHardwareAsync(),
			LocalAuthentication.isEnrolledAsync(),
		]);
		return hasHardware && enrolled;
	} catch {
		return false;
	}
}

/**
 * Prompts the user to unlock the app. Resolves true only when the device
 * reports a successful authentication.
 */
export async function unlockApp(): Promise<boolean> {
	try {
		const result = await LocalAuthentication.authenticateAsync({
			promptMessage: "Unlock SHADOW",
			fallbackLabel: "Use passcode",
			disableDeviceFallback: false,
		});
		return result.success;
	} catch {
		return false;
	}
}
