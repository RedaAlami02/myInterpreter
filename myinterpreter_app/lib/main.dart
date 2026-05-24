import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'appwrite_client.dart';
import 'screens/login.dart';
import 'screens/home.dart';

// ─── Design tokens ────────────────────────────────────────────────────────────
const kBg         = Color(0xFF0D1117);
const kSurface     = Color(0xFF161B22);
const kSurfaceHigh = Color(0xFF21262D);
const kAccent      = Color(0xFFD4A017);
const kTextPrimary = Color(0xFFE6EDF3);
const kTextMuted   = Color(0xFF8B949E);
const kPositive    = Color(0xFF3FB950);
const kNegative    = Color(0xFFF85149);
const kBorder      = Color(0xFF30363D);

ThemeData buildTheme() {
  final base = GoogleFonts.interTextTheme(const TextTheme(
    displayLarge:   TextStyle(color: kTextPrimary, fontWeight: FontWeight.w700, fontSize: 32),
    headlineMedium: TextStyle(color: kTextPrimary, fontWeight: FontWeight.w700, fontSize: 24),
    titleLarge:     TextStyle(color: kTextPrimary, fontWeight: FontWeight.w600, fontSize: 18),
    titleMedium:    TextStyle(color: kTextPrimary, fontWeight: FontWeight.w600, fontSize: 16),
    bodyLarge:      TextStyle(color: kTextPrimary, fontWeight: FontWeight.w400, fontSize: 16),
    bodyMedium:     TextStyle(color: kTextPrimary, fontWeight: FontWeight.w400, fontSize: 14),
    bodySmall:      TextStyle(color: kTextMuted,   fontWeight: FontWeight.w400, fontSize: 12),
    labelLarge:     TextStyle(color: kBg,          fontWeight: FontWeight.w600, fontSize: 14),
    labelSmall:     TextStyle(color: kTextMuted,   fontWeight: FontWeight.w500, fontSize: 11),
  ));

  const scheme = ColorScheme(
    brightness: Brightness.dark,
    primary: kAccent,
    onPrimary: kBg,
    primaryContainer: kSurfaceHigh,
    onPrimaryContainer: kTextPrimary,
    secondary: kAccent,
    onSecondary: kBg,
    secondaryContainer: kSurfaceHigh,
    onSecondaryContainer: kTextPrimary,
    tertiary: kPositive,
    onTertiary: kBg,
    surface: kSurface,
    onSurface: kTextPrimary,
    onSurfaceVariant: kTextMuted,
    error: kNegative,
    onError: kBg,
    outline: kBorder,
    outlineVariant: kBorder,
    shadow: Colors.black,
    scrim: Colors.black87,
    inverseSurface: kTextPrimary,
    onInverseSurface: kBg,
    inversePrimary: kAccent,
    surfaceContainerHighest: kSurfaceHigh,
    surfaceContainerHigh: kSurfaceHigh,
    surfaceContainer: kSurface,
    surfaceContainerLow: kSurface,
    surfaceContainerLowest: kBg,
  );

  return ThemeData(
    useMaterial3: true,
    brightness: Brightness.dark,
    colorScheme: scheme,
    scaffoldBackgroundColor: kBg,
    textTheme: base,
    appBarTheme: AppBarTheme(
      backgroundColor: kSurface,
      foregroundColor: kTextPrimary,
      titleTextStyle: GoogleFonts.inter(
        color: kAccent, fontSize: 18, fontWeight: FontWeight.w700),
      elevation: 0,
      shadowColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      iconTheme: const IconThemeData(color: kTextMuted),
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: kSurface,
      indicatorColor: kAccent.withValues(alpha: 0.2),
      iconTheme: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return const IconThemeData(color: kAccent);
        }
        return const IconThemeData(color: kTextMuted);
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.selected)) {
          return GoogleFonts.inter(color: kAccent, fontSize: 12, fontWeight: FontWeight.w600);
        }
        return GoogleFonts.inter(color: kTextMuted, fontSize: 12);
      }),
      surfaceTintColor: Colors.transparent,
      elevation: 0,
    ),
    cardTheme: CardThemeData(
      color: kSurface,
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: const BorderSide(color: kBorder, width: 1),
      ),
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: kAccent,
        foregroundColor: kBg,
        textStyle: GoogleFonts.inter(fontWeight: FontWeight.w600, fontSize: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
        elevation: 0,
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: kSurfaceHigh,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: kBorder),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: kBorder),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: kAccent, width: 1.5),
      ),
      labelStyle: const TextStyle(color: kTextMuted),
      hintStyle: const TextStyle(color: kTextMuted),
      prefixIconColor: kTextMuted,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
    ),
    chipTheme: ChipThemeData(
      backgroundColor: kSurfaceHigh,
      selectedColor: kAccent.withValues(alpha: 0.2),
      labelStyle: GoogleFonts.inter(color: kTextMuted, fontSize: 12),
      secondaryLabelStyle: GoogleFonts.inter(color: kAccent, fontSize: 12, fontWeight: FontWeight.w600),
      side: const BorderSide(color: kBorder),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      padding: const EdgeInsets.symmetric(horizontal: 4),
    ),
    dividerTheme: const DividerThemeData(color: kBorder, thickness: 1, space: 1),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      elevation: 2,
    ),
  );
}

void main() => runApp(const MyApp());

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'myInterpreter',
    theme: buildTheme(),
    home: const _AuthGate(),
    debugShowCheckedModeBanner: false,
  );
}

class _AuthGate extends StatefulWidget {
  const _AuthGate();
  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  late final Future _future = _checkAuth();

  Future _checkAuth() async {
    try {
      const storage = FlutterSecureStorage();
      final stay = await storage.read(key: 'stay_logged_in');
      if (stay == 'false') {
        // User opted out of staying logged in — log them out
        await storage.delete(key: 'stay_logged_in');
        try { await account.deleteSession(sessionId: 'current'); } catch (_) {}
        throw Exception('not staying logged in');
      }
      print('DEBUG auth: checking session...');
      final me = await account.get();
      print('DEBUG auth: logged in as ${me.$id}');
      return me;
    } catch (e) {
      print('DEBUG auth: not logged in — $e');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) => FutureBuilder(
    future: _future,
    builder: (ctx, snap) {
      if (snap.connectionState != ConnectionState.done) {
        return const Scaffold(body: Center(child: CircularProgressIndicator(color: kAccent)));
      }
      if (snap.hasError) return const LoginScreen();
      if (snap.hasData) return const HomeScreen();
      return const LoginScreen();
    },
  );
}
