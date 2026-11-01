import 'dart:async';
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:myinterpreter_app/backend_contract.dart';
import 'package:myinterpreter_app/mobile_email_auth.dart';
import 'package:myinterpreter_app/secure_session_storage.dart';
import 'package:myinterpreter_app/supabase_backend.dart';

import 'supabase_backend_test.dart'
    show fixtureUrl, fixtureKey, fixtureUser, fixtureSession, jsonResponse;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late SupabaseClient client;
  late SupabaseBackend backend;
  late SecureSessionStorage storage;
  late DateTime clock;
  late Future<http.Response> Function(http.Request) respond;
  final calls = <http.Request>[];
  final confirmedUser = {
    ...fixtureUser,
    'email_confirmed_at': '2026-01-01T00:00:00Z',
  };

  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    storage = SecureSessionStorage('email-auth-fixture');
    clock = DateTime.utc(2026, 10, 29, 10);
    calls.clear();
    respond = (request) async {
      final path = request.url.path;
      if (path.endsWith('/token')) {
        return jsonResponse(
          jsonEncode({...fixtureSession(), 'user': confirmedUser}),
          200,
        );
      }
      if (path.endsWith('/user')) {
        return jsonResponse(jsonEncode(confirmedUser), 200);
      }
      if (path.endsWith('/signup')) {
        return jsonResponse(jsonEncode(confirmedUser), 200);
      }
      return jsonResponse('{}', 200);
    };
    client = SupabaseClient(
      fixtureUrl,
      fixtureKey,
      authOptions: AuthClientOptions(
        autoRefreshToken: false,
        authFlowType: AuthFlowType.pkce,
        pkceAsyncStorage: SecurePkceStorage('email-auth-fixture'),
      ),
      httpClient: MockClient((request) async {
        calls.add(request);
        final response = await respond(request);
        return http.Response.bytes(
          response.bodyBytes,
          response.statusCode,
          headers: response.headers,
          request: request,
        );
      }),
    );
    backend = SupabaseBackend(
      client,
      storage,
      emailLinksEnabled: true,
      clock: () => clock,
    );
  });
  tearDown(() async => client.dispose());

  final callback = Uri.parse('$mobileAuthCallback?code=fixture-code');
  Future<void> recovery() =>
      backend.requestPasswordReset('fixture@example.invalid');
  Future<void> completeRecovery() async {
    await recovery();
    expect(
      await backend.completeEmailLink(callback),
      EmailLinkOutcome.passwordRecovery,
    );
  }

  test('disabled by default and accepts no emailed tokens', () async {
    final disabled = SupabaseBackend(client, storage);
    expect(disabled.emailLinksEnabled, isFalse);
    await expectLater(
      disabled.requestPasswordReset('fixture@example.invalid'),
      throwsA(isA<BackendFailure>()),
    );
    await expectLater(
      disabled.completeEmailLink(callback),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls, isEmpty);
  });

  test('callback validates exact endpoint, one code and no fragment', () {
    expect(mobileAuthCode(callback), 'fixture-code');
    for (final value in [
      'https://auth/callback?code=x',
      'com.myinterpreter.app://other/callback?code=x',
      'com.myinterpreter.app://auth/elsewhere?code=x',
      'com.myinterpreter.app://user@auth/callback?code=x',
      'com.myinterpreter.app://auth:443/callback?code=x',
      '$mobileAuthCallback?code=x&code=y',
      '$mobileAuthCallback?code=x&type=recovery',
      '$mobileAuthCallback?code=x#access_token=forged',
      '$mobileAuthCallback#access_token=forged',
      '$mobileAuthCallback?code=',
      '$mobileAuthCallback?code=%0Asecret',
      '$mobileAuthCallback?error_description=private',
    ]) {
      expect(
        () => mobileAuthCode(Uri.parse(value)),
        throwsA(isA<BackendFailure>()),
        reason: value,
      );
    }
  });

  test(
    'requires same-device pending intent before any code exchange',
    () async {
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
      expect(calls, isEmpty);
    },
  );

  test('reset and resend use S256, fixed redirect and no password', () async {
    await recovery();
    var request = calls.single;
    var body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(request.url.path, '/auth/v1/recover');
    expect(request.url.queryParameters['redirect_to'], mobileAuthCallback);
    expect(body['code_challenge_method'], 's256');
    expect(body['code_challenge'], isNotEmpty);
    expect(body.containsKey('password'), isFalse);
    await backend.resendConfirmation('fixture@example.invalid');
    request = calls.last;
    body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(request.url.path, '/auth/v1/resend');
    expect(body['type'], 'signup');
    expect(body['code_challenge_method'], 's256');
    expect(request.url.queryParameters['redirect_to'], mobileAuthCallback);
  });

  test(
    'confirmation validates user then signs out without claiming portfolio',
    () async {
      final outcome = await backend.signUp(
        email: 'fixture@example.invalid',
        password: 'fixture-password',
        name: 'Fixture',
        remember: true,
      );
      expect(outcome, SignUpOutcome.confirmationRequired);
      expect(
        calls.single.url.queryParameters['redirect_to'],
        mobileAuthCallback,
      );
      expect(
        await backend.completeEmailLink(callback),
        EmailLinkOutcome.confirmed,
      );
      expect(calls.map((r) => r.url.path), [
        '/auth/v1/signup',
        '/auth/v1/token',
        '/auth/v1/user',
        '/auth/v1/logout',
      ]);
      expect(client.auth.currentSession, isNull);
      expect(await storage.hasAccessToken(), isFalse);
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
    },
  );

  test(
    'recovery is temporary and blocks data, trades, login and restore',
    () async {
      await completeRecovery();
      expect(backend.hasRecoverySession, isTrue);
      expect(await storage.hasAccessToken(), isFalse);
      calls.clear();
      await expectLater(backend.restoreUser(), throwsA(isA<BackendFailure>()));
      await expectLater(
        backend.listDocuments(collectionId: 'company'),
        throwsA(isA<BackendFailure>()),
      );
      await expectLater(
        backend.recordTrade(
          requestId: 'x',
          isBuy: true,
          company: 'Fixture',
          quantity: '1',
          price: '1',
        ),
        throwsA(isA<BackendFailure>()),
      );
      await expectLater(
        backend.signIn(
          email: 'fixture@example.invalid',
          password: 'fixture-password',
          remember: true,
        ),
        throwsA(isA<BackendFailure>()),
      );
      expect(calls, isEmpty);
    },
  );

  test(
    'only valid recovery can update password; then sign-in is required',
    () async {
      await completeRecovery();
      calls.clear();
      await backend.updateRecoveredPassword('new-fixture-password');
      expect(calls.map((r) => r.method), ['GET', 'PUT', 'POST']);
      expect(jsonDecode(calls[1].body), {'password': 'new-fixture-password'});
      expect(client.auth.currentSession, isNull);
      expect(backend.hasRecoverySession, isFalse);
      expect(await storage.hasAccessToken(), isFalse);
      await expectLater(
        backend.updateRecoveredPassword('another-password'),
        throwsA(isA<BackendFailure>()),
      );
    },
  );

  test('short or excessive password never reaches user update', () async {
    await completeRecovery();
    calls.clear();
    for (final password in ['short', 'x' * 129]) {
      await expectLater(
        backend.updateRecoveredPassword(password),
        throwsA(isA<BackendFailure>()),
      );
    }
    expect(calls, isEmpty);
    expect(backend.hasRecoverySession, isTrue);
  });

  test(
    'expiry is exclusive and clock rollback cannot admit old requests',
    () async {
      await recovery();
      calls.clear();
      clock = clock.add(const Duration(hours: 1));
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
      expect(calls, isEmpty);
      await recovery();
      calls.clear();
      clock = clock.subtract(const Duration(seconds: 1));
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
      expect(calls, isEmpty);
    },
  );

  test('recovery expires at 15 minutes and requires a new request', () async {
    await completeRecovery();
    clock = clock.add(const Duration(minutes: 15));
    expect(backend.hasRecoverySession, isFalse);
    calls.clear();
    await expectLater(
      backend.updateRecoveredPassword('new-fixture-password'),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls.where((r) => r.method == 'PUT'), isEmpty);
    expect(client.auth.currentSession, isNull);
    await completeRecovery();
    clock = clock.subtract(const Duration(seconds: 1));
    expect(backend.hasRecoverySession, isFalse);
    calls.clear();
    await expectLater(
      backend.updateRecoveredPassword('new-fixture-password'),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls.where((r) => r.method == 'PUT'), isEmpty);
    expect(client.auth.currentSession, isNull);
  });

  test(
    'intent/type mismatch is rejected and provisional session cleared',
    () async {
      await recovery();
      // Replacing the verifier with a signup verifier cannot confer recovery intent.
      await client.auth.resend(
        email: 'fixture@example.invalid',
        type: OtpType.signup,
      );
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
      expect(client.auth.currentSession, isNull);
      expect(await storage.hasAccessToken(), isFalse);
    },
  );

  test('different or unconfirmed remote email cannot claim session', () async {
    for (final user in [
      {...confirmedUser, 'email': 'other@example.invalid'},
      {...confirmedUser, 'email_confirmed_at': null},
      {...confirmedUser, 'id': 'other-user'},
    ]) {
      await recovery();
      final previous = respond;
      respond = (request) async => request.url.path.endsWith('/user')
          ? jsonResponse(jsonEncode(user), 200)
          : previous(request);
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
      expect(client.auth.currentSession, isNull);
      respond = previous;
    }
  });

  test(
    'a fresh controller can complete securely persisted intent after restart',
    () async {
      await recovery();
      backend = SupabaseBackend(
        client,
        storage,
        emailLinksEnabled: true,
        clock: () => clock,
      );
      expect(
        await backend.completeEmailLink(callback),
        EmailLinkOutcome.passwordRecovery,
      );
      await backend.cancelEmailRecovery();
      expect(client.auth.currentSession, isNull);
      await expectLater(
        backend.completeEmailLink(callback),
        throwsA(isA<BackendFailure>()),
      );
    },
  );

  test('ordinary login invalidates an outstanding email callback', () async {
    await recovery();
    await backend.signIn(
      email: 'fixture@example.invalid',
      password: 'fixture-password',
      remember: true,
    );
    await backend.signOut();
    calls.clear();
    await expectLater(
      backend.completeEmailLink(callback),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls, isEmpty);
  });

  test(
    'request and password sign-in cannot race an in-flight exchange',
    () async {
      await recovery();
      final gate = Completer<http.Response>();
      final previous = respond;
      respond = (request) =>
          request.url.path.endsWith('/token') ? gate.future : previous(request);
      final completing = backend.completeEmailLink(callback);
      while (!calls.any((r) => r.url.path.endsWith('/token'))) {
        await Future<void>.delayed(Duration.zero);
      }
      await expectLater(recovery(), throwsA(isA<BackendFailure>()));
      await expectLater(
        backend.signIn(
          email: 'fixture@example.invalid',
          password: 'fixture-password',
          remember: true,
        ),
        throwsA(isA<BackendFailure>()),
      );
      await expectLater(backend.getUser(), throwsA(isA<BackendFailure>()));
      gate.complete(
        jsonResponse(
          jsonEncode({...fixtureSession(), 'user': confirmedUser}),
          200,
        ),
      );
      expect(await completing, EmailLinkOutcome.passwordRecovery);
      expect(await storage.hasAccessToken(), isFalse);
    },
  );

  test('upstream response details are never included in errors', () async {
    respond = (_) async =>
        jsonResponse('{"msg":"fixture-secret-and-private-host"}', 500);
    try {
      await recovery();
      fail('Expected a sanitized error');
    } on BackendFailure catch (error) {
      expect(error.message, isNot(contains('fixture-secret')));
      expect(error.message, isNot(contains('private-host')));
    }
  });
}
