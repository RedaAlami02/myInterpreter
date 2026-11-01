import 'dart:convert';

import 'package:supabase_flutter/supabase_flutter.dart';

import 'backend_contract.dart';
import 'secure_session_storage.dart';

const mobileAuthCallback = 'com.myinterpreter.app://auth/callback';

/// Deliberately accepts PKCE only. Never adopt bearer tokens from an incoming URL.
String mobileAuthCode(Uri uri) {
  if (uri.scheme != 'com.myinterpreter.app' ||
      uri.host != 'auth' ||
      uri.path != '/callback' ||
      uri.userInfo.isNotEmpty ||
      uri.hasPort ||
      uri.hasFragment ||
      uri.queryParametersAll.length != 1 ||
      uri.queryParametersAll['code']?.length != 1) {
    throw const BackendFailure(
      'This email link is invalid. Request a new link.',
    );
  }
  final code = uri.queryParameters['code']!;
  if (!RegExp(r'^[A-Za-z0-9._~-]{1,2048}$').hasMatch(code)) {
    throw const BackendFailure(
      'This email link is invalid. Request a new link.',
    );
  }
  return code;
}

/// The SDK holds the PKCE verifier in project-scoped secure storage. This record
/// binds its one outstanding flow to an intent, email and bounded start time.
/// Codes, passwords and recovery sessions are never stored in this record.
class MobileEmailAuth {
  final SupabaseClient client;
  final SecureSessionStorage sessions;
  final bool enabled;
  final DateTime Function() now;
  bool _busy = false;
  bool _exchanging = false;
  String? _recoveryUser;
  DateTime? _recoveryStarted;
  DateTime? _recoveryUntil;

  MobileEmailAuth(
    this.client,
    this.sessions, {
    this.enabled = false,
    DateTime Function()? clock,
  }) : now = clock ?? DateTime.now;

  String get _pendingKey => '${sessions.namespace}.email-flow';
  bool get blocksApplication => _exchanging || _recoveryUser != null;
  bool get hasRecoverySession =>
      _recoveryUser != null &&
      client.auth.currentUser?.id == _recoveryUser &&
      _recoveryStarted != null &&
      !now().isBefore(_recoveryStarted!) &&
      _recoveryUntil != null &&
      now().isBefore(_recoveryUntil!);

  Future<T> _guard<T>(Future<T> Function() action) async {
    if (!enabled) {
      throw const BackendFailure('Mobile email links are not enabled yet.');
    }
    if (_busy) {
      throw const BackendFailure(
        'An authentication request is already running.',
      );
    }
    _busy = true;
    try {
      return await action();
    } on BackendFailure {
      rethrow;
    } catch (_) {
      // In particular, SDK exceptions can contain URLs or upstream response text.
      throw const BackendFailure(
        'Email authentication could not be completed. Please retry.',
      );
    } finally {
      _busy = false;
    }
  }

  Future<void> _begin(String kind, String email) async {
    if (client.auth.currentSession != null || blocksApplication) {
      throw const BackendFailure('Sign out before requesting an email link.');
    }
    final address = email.trim();
    if (address.length > 254 ||
        !RegExp(r'^[^\s@]+@[^\s@]+\.[^\s@]+$').hasMatch(address)) {
      throw const BackendFailure('Enter a valid email address.');
    }
    // The SDK can emit signedIn before our /user validation. No provisional
    // session may be persisted by its auth-state listener, even after a crash.
    await sessions.setRemember(false);
    await sessions.storage.write(
      key: _pendingKey,
      value: jsonEncode({
        'kind': kind,
        'email': address.toLowerCase(),
        'started_at': now().toUtc().toIso8601String(),
      }),
    );
  }

  Future<SignUpOutcome> signUp({
    required String email,
    required String password,
    required String name,
    required bool remember,
  }) => _guard(() async {
    await _begin('confirmation', email);
    try {
      final result = await client.auth.signUp(
        email: email.trim(),
        password: password,
        data: {'name': name},
        emailRedirectTo: mobileAuthCallback,
      );
      if (result.session == null) return SignUpOutcome.confirmationRequired;
      await sessions.storage.delete(key: _pendingKey);
      await sessions.setRemember(remember);
      await sessions.persistSession(jsonEncode(result.session!.toJson()));
      return SignUpOutcome.signedIn;
    } catch (_) {
      await _discard();
      rethrow;
    }
  });

  Future<void> requestPasswordReset(String email) => _guard(() async {
    await _begin('recovery', email);
    try {
      // Same success response for existing and nonexistent addresses.
      await client.auth.resetPasswordForEmail(
        email.trim(),
        redirectTo: mobileAuthCallback,
      );
    } catch (_) {
      await _discard();
      rethrow;
    }
  });

  Future<void> resendConfirmation(String email) => _guard(() async {
    await _begin('confirmation', email);
    try {
      await client.auth.resend(
        email: email.trim(),
        type: OtpType.signup,
        emailRedirectTo: mobileAuthCallback,
      );
    } catch (_) {
      await _discard();
      rethrow;
    }
  });

  Future<EmailLinkOutcome> complete(Uri uri) => _guard(() async {
    final code = mobileAuthCode(uri);
    if (client.auth.currentSession != null || blocksApplication) {
      throw const BackendFailure('Sign out before opening an email link.');
    }
    final stored = await sessions.storage.read(key: _pendingKey);
    if (stored == null) {
      throw const BackendFailure('Request a new email link on this device.');
    }
    _exchanging = true;
    try {
      final pending = jsonDecode(stored) as Map<String, dynamic>;
      final kind = pending['kind'];
      final started = DateTime.parse(pending['started_at'] as String);
      final age = now().toUtc().difference(started);
      if (!['confirmation', 'recovery'].contains(kind) ||
          age.isNegative ||
          age >= const Duration(hours: 1)) {
        throw const BackendFailure('This email request expired. Start again.');
      }
      await sessions.setRemember(false);
      final result = await client.auth.exchangeCodeForSession(code);
      if ((kind == 'recovery') !=
          (result.redirectType == AuthChangeEvent.passwordRecovery.name)) {
        throw const BackendFailure(
          'This email link does not match the request.',
        );
      }
      final user = (await client.auth.getUser()).user;
      if (user == null ||
          user.id != result.session.user.id ||
          user.email?.toLowerCase() != pending['email'] ||
          user.emailConfirmedAt == null) {
        throw const BackendFailure(
          'This email link does not match the account.',
        );
      }
      await sessions.storage.delete(key: _pendingKey);
      if (kind == 'recovery') {
        _recoveryUser = user.id;
        _recoveryStarted = now();
        _recoveryUntil = _recoveryStarted!.add(const Duration(minutes: 15));
        return EmailLinkOutcome.passwordRecovery;
      }
      // Confirmation completes ownership verification, then normal password
      // sign-in decides persistence. It never automatically claims a portfolio.
      await _discard();
      return EmailLinkOutcome.confirmed;
    } catch (_) {
      await _discard();
      rethrow;
    } finally {
      _exchanging = false;
    }
  });

  Future<void> updatePassword(String password) => _guard(() async {
    if (!hasRecoverySession) {
      await _discard();
      throw const BackendFailure('Recovery expired. Request a new email link.');
    }
    if (password.length < 8 || password.length > 128) {
      throw const BackendFailure(
        'Use a password between 8 and 128 characters.',
      );
    }
    final user = (await client.auth.getUser()).user;
    if (user?.id != _recoveryUser) {
      await _discard();
      throw const BackendFailure('Recovery expired. Request a new email link.');
    }
    final result = await client.auth.updateUser(
      UserAttributes(password: password),
    );
    if (result.user?.id != _recoveryUser) {
      await _discard();
      throw const BackendFailure('Password change could not be verified.');
    }
    await _discard();
  });

  /// Invalidates outstanding links when choosing ordinary password sign-in.
  Future<void> passwordSignIn(Future<void> Function() action) => _guard(
    () async {
      if (blocksApplication) {
        throw const BackendFailure('Finish or cancel password recovery first.');
      }
      await sessions.storage.delete(key: _pendingKey);
      await action();
    },
  );

  Future<void> cancel() => _guard(_discard);

  Future<void> _discard() async {
    await sessions.setRemember(false);
    await sessions.storage.delete(key: _pendingKey);
    try {
      // SDK removes the in-memory session and PKCE verifier before revocation.
      await client.auth.signOut(scope: SignOutScope.local);
    } catch (_) {
      throw const BackendFailure(
        'Signed out on this device. Server revocation could not be confirmed.',
        signedOut: true,
      );
    } finally {
      _recoveryUser = null;
      _recoveryStarted = null;
      _recoveryUntil = null;
    }
  }
}
