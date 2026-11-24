import 'package:supabase_flutter/supabase_flutter.dart';

import 'backend_contract.dart';
import 'secure_session_storage.dart';
import 'supabase_backend.dart';

export 'backend_contract.dart';

AppBackend backend = _UnconfiguredBackend();

class _UnconfiguredBackend implements AppBackend {
  Never _missing() =>
      throw const BackendFailure('Backend configuration is required.');
  @override
  Future<AppUser> restoreUser() async => _missing();
  @override
  Future<AppUser> getUser() async => _missing();
  @override
  Future<void> signIn({
    required String email,
    required String password,
    required bool remember,
  }) async => _missing();
  @override
  Future<SignUpOutcome> signUp({
    required String email,
    required String password,
    required String name,
    required bool remember,
  }) async => _missing();
  @override
  Future<void> signOut() async => _missing();
  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async => _missing();
  @override
  Future<void> recordTrade({
    required String requestId,
    required bool isBuy,
    required String company,
    required String quantity,
    required String price,
  }) async => _missing();
}

Future<void> initializeBackend() async {
  const selected = String.fromEnvironment(
    'MYINTERPRETER_BACKEND',
    defaultValue: 'supabase',
  );
  if (selected != 'supabase') {
    throw const BackendFailure('Unknown application backend.');
  }
  const url = String.fromEnvironment('SUPABASE_PROJECT_URL');
  const key = String.fromEnvironment('SUPABASE_PUBLISHABLE_KEY');
  validateSupabaseConfiguration(url, key);
  final namespace =
      'myinterpreter.supabase.${Uri.parse(url).host.split('.').first}';
  final storage = SecureSessionStorage(namespace);
  await Supabase.initialize(
    url: url,
    publishableKey: key,
    debug: false,
    authOptions: FlutterAuthClientOptions(
      localStorage: storage,
      pkceAsyncStorage: SecurePkceStorage(namespace),
      // MobileEmailAuth and AppLinks validate locally initiated PKCE callbacks.
      // Leave SDK auto-adoption off so links cannot bypass that intent check.
      detectSessionInUri: false,
      authFlowType: AuthFlowType.pkce,
    ),
  );
  backend = SupabaseBackend(
    Supabase.instance.client,
    storage,
    portfolioRecoveryEnabled: true,
    emailLinksEnabled: const bool.fromEnvironment(
      'MYINTERPRETER_MOBILE_AUTH_LINKS',
      defaultValue: false,
    ),
    marketDisplayEnabled: const bool.fromEnvironment(
      'MYINTERPRETER_MARKET_PREVIEW',
      defaultValue: false,
    ),
  );
}
