import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

/// Project-scoped storage prevents legacy or other-project sessions being reused.
/// Opting out of persistence keeps the SDK session in memory for this run only.
class SecureSessionStorage extends LocalStorage {
  final FlutterSecureStorage storage;
  final String namespace;
  SecureSessionStorage(
    this.namespace, {
    this.storage = const FlutterSecureStorage(),
  });
  Future<void> _pending = Future<void>.value();

  Future<void> _write(Future<void> Function() operation) {
    final result = _pending.then((_) => operation());
    _pending = result.then(
      (_) {},
      onError: (Object error, StackTrace stack) {},
    );
    return result;
  }

  String get sessionKey => '$namespace.session';
  String get rememberKey => '$namespace.remember';

  Future<void> setRemember(bool remember) => _write(() async {
    await storage.write(key: rememberKey, value: remember ? 'true' : 'false');
    if (!remember) await storage.delete(key: sessionKey);
  });

  Future<bool> get _remember async =>
      await storage.read(key: rememberKey) == 'true';

  @override
  Future<void> initialize() async {}
  @override
  Future<bool> hasAccessToken() async => await accessToken() != null;
  @override
  Future<String?> accessToken() async {
    await _pending;
    return await _remember ? storage.read(key: sessionKey) : null;
  }

  @override
  Future<void> removePersistedSession() =>
      _write(() => storage.delete(key: sessionKey));
  @override
  Future<void> persistSession(String persistSessionString) => _write(() async {
    if (await _remember) {
      await storage.write(key: sessionKey, value: persistSessionString);
    } else {
      await storage.delete(key: sessionKey);
    }
  });
}

class SecurePkceStorage extends GotrueAsyncStorage {
  final String namespace;
  final FlutterSecureStorage storage;
  SecurePkceStorage(
    this.namespace, {
    this.storage = const FlutterSecureStorage(),
  });
  @override
  Future<String?> getItem({required String key}) =>
      storage.read(key: '$namespace.pkce.$key');
  @override
  Future<void> setItem({required String key, required String value}) =>
      storage.write(key: '$namespace.pkce.$key', value: value);
  @override
  Future<void> removeItem({required String key}) =>
      storage.delete(key: '$namespace.pkce.$key');
}
