const IS_DEV = process.env.APP_VARIANT === 'development';
const IS_PREVIEW = process.env.APP_VARIANT === 'preview';

const getAppName = () => {
  if (IS_DEV) return 'SHADOW Dev';
  if (IS_PREVIEW) return 'SHADOW Preview';
  return 'SHADOW';
};

const getBundleId = () => {
  if (IS_DEV) return 'ai.shadow.app.dev';
  if (IS_PREVIEW) return 'ai.shadow.app.preview';
  return 'ai.shadow.app';
};

const getAndroidPackage = () => {
  if (IS_DEV) return 'ai.shadow.app.dev';
  if (IS_PREVIEW) return 'ai.shadow.app.preview';
  return 'ai.shadow.app';
};

export default {
  expo: {
    name: getAppName(),
    slug: 'shadow',
    version: '1.0.0',
    orientation: 'portrait',
    icon: './assets/icon.png',
    scheme: 'shadow',
    userInterfaceStyle: 'automatic',
    newArchEnabled: true,
    platforms: ['ios', 'android'],
    splash: {
      image: './assets/splash.png',
      resizeMode: 'contain',
      backgroundColor: '#0A0A0A',
    },
    ios: {
      supportsTablet: true,
      bundleIdentifier: getBundleId(),
      buildNumber: '1',
      infoPlist: {
        NSCameraUsageDescription:
          'SHADOW needs camera access to scan QR codes for node pairing',
        NSFaceIDUsageDescription:
          'SHADOW uses Face ID to protect your device identity and approvals',
        NSLocalNetworkUsageDescription:
          'SHADOW discovers Shadow Nodes on your local network',
        NSBonjourServices: ['_shadow._tcp', '_http._tcp'],
        NSAppTransportSecurity: {
          NSAllowsArbitraryLoads: true,
          NSAllowsLocalNetworking: true,
        },
      },
      config: {
        usesNonExemptEncryption: false,
      },
    },
    android: {
      package: getAndroidPackage(),
      adaptiveIcon: {
        foregroundImage: './assets/adaptive-icon.png',
        backgroundColor: '#0A0A0A',
      },
      permissions: [],
    },
    plugins: [
      'expo-router',
      '@avasapp/react-native-app-intents',
      './plugins/withSystemIntegrations.js',
      [
        'expo-splash-screen',
        {
          backgroundColor: '#0A0A0A',
          image: './assets/splash.png',
          imageWidth: 200,
        },
      ],
      [
        'expo-font',
        {
          fonts: [
            './assets/fonts/IBMPlexSans-Regular.ttf',
            './assets/fonts/IBMPlexSans-Medium.ttf',
            './assets/fonts/IBMPlexSans-SemiBold.ttf',
            './assets/fonts/IBMPlexSans-Bold.ttf',
            './assets/fonts/IBMPlexMono-Regular.ttf',
            './assets/fonts/IBMPlexMono-Medium.ttf',
            './assets/fonts/IBMPlexMono-SemiBold.ttf',
            './assets/fonts/IBMPlexMono-Bold.ttf',
          ],
        },
      ],
      'expo-secure-store',
      [
        'expo-camera',
        {
          cameraPermission:
            'Allow SHADOW to access your camera to scan the node pairing QR code',
        },
      ],
      [
        'expo-local-authentication',
        {
          faceIDPermission:
            'Allow SHADOW to use Face ID to protect approvals',
        },
      ],
      [
        'expo-notifications',
        {
          icon: './assets/notification-icon.png',
          color: '#0A0A0A',
          sounds: [],
        },
      ],
      [
        'expo-file-system',
        {
          supportsOpeningDocumentsInPlace: true,
          enableFileSharing: true,
        },
      ],
    ],
    experiments: {
      typedRoutes: true,
    },
    extra: {
      router: {
        origin: false,
      },
      eas: {
        // Inan replaces this with his EAS project id from https://expo.dev
        // before building; push tokens cannot be issued without it.
        projectId: 'TODO-inan-eas-project-id',
      },
    },
  },
};
