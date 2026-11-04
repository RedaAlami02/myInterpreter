import 'dart:convert';
import 'dart:io';
import 'package:myinterpreter_app/portfolio_prices.dart';

import 'package:myinterpreter_app/query.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'package:myinterpreter_app/backend_contract.dart';
import 'package:myinterpreter_app/secure_session_storage.dart';
import 'package:myinterpreter_app/supabase_backend.dart';

http.Response jsonResponse(String body, int status) =>
    http.Response(body, status, headers: {'content-type': 'application/json'});

const fixtureUrl = 'https://abcdefghijklmnopqrst.supabase.co';
const fixtureKey = 'sb_publishable_fixture_only';
final fixtureUser = {
  'id': 'fixture-user',
  'email': 'fixture@example.invalid',
  'aud': 'authenticated',
  'created_at': '2026-01-01T00:00:00Z',
};
String fixtureJwt({bool expired = false}) {
  String encode(Object value) =>
      base64Url.encode(utf8.encode(jsonEncode(value))).replaceAll('=', '');
  return '${encode({'alg': 'HS256', 'typ': 'JWT'})}.${encode({'sub': 'fixture-user', 'exp': DateTime.now().millisecondsSinceEpoch ~/ 1000 + (expired ? -60 : 3600)})}.fixture-signature';
}

Map<String, dynamic> fixtureSession({bool expired = false}) => {
  'access_token': fixtureJwt(expired: expired),
  'refresh_token': 'fixture-refresh',
  'expires_in': 3600,
  'token_type': 'bearer',
  'user': fixtureUser,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late SupabaseClient client;
  late SupabaseBackend backend;
  late SecureSessionStorage storage;
  late Future<http.Response> Function(http.Request request) respond;
  final calls = <http.Request>[];
  setUp(() {
    FlutterSecureStorage.setMockInitialValues({});
    storage = SecureSessionStorage('fixture-project');
    calls.clear();
    respond = (request) async => jsonResponse('{}', 500);
    client = SupabaseClient(
      fixtureUrl,
      fixtureKey,
      authOptions: AuthClientOptions(
        autoRefreshToken: false,
        pkceAsyncStorage: SecurePkceStorage('fixture-project'),
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
    backend = SupabaseBackend(client, storage);
  });
  tearDown(() async {
    await client.dispose();
  });
  Future<void> login({bool remember = true}) async {
    respond = (_) async => jsonResponse(jsonEncode(fixtureSession()), 200);
    await backend.signIn(
      email: 'fixture@example.invalid',
      password: 'fixture-password',
      remember: remember,
    );
    calls.clear();
  }

  test(
    'verified reference RPC preserves filters, pagination and safe projection',
    () async {
      await login();
      respond = (request) async {
        expect(request.method, 'GET');
        expect(
          request.url.path,
          '/rest/v1/rpc/read_latest_price_references_v1',
        );
        expect(request.url.queryParameters['c_name'], 'eq.SGTM');
        expect(request.url.queryParameters['order'], contains('date.desc'));
        final offset = int.parse(request.url.queryParameters['offset']!);
        return jsonResponse(
          jsonEncode(
            List.generate(
              offset == 5 ? 500 : 1,
              (i) => {
                'id': 'close:${offset + i}',
                'c_name': 'SGTM',
                'pa': 524,
                'date': '2026-11-03T19:23:21Z',
                'origin_collection': 'verified_official_close_display/v1',
                'raw_pdf': 'private-fixture',
              },
            ),
          ),
          200,
        );
      };
      final result = await backend.listDocuments(
        collectionId: 'latest_prices',
        queries: [
          Query.equal('c_name', 'SGTM'),
          Query.orderDesc('date'),
          Query.offset(5),
          Query.limit(501),
        ],
      );
      expect(result.documents, hasLength(501));
      expect(calls.map((r) => r.url.queryParameters['offset']), ['5', '505']);
      expect(result.documents.first.data.containsKey('raw_pdf'), isFalse);
    },
  );
  test('reference failure never falls back to stale original table', () async {
    await login();
    respond = (_) async => jsonResponse('{}', 403);
    await expectLater(
      backend.listDocuments(collectionId: 'latest_prices'),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls, isNotEmpty);
    expect(
      calls.every(
        (r) => r.url.path == '/rest/v1/rpc/read_latest_price_references_v1',
      ),
      isTrue,
    );
  });
  test('reference RPC requires a session before any request', () async {
    await expectLater(
      backend.listDocuments(collectionId: 'latest_prices'),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls, isEmpty);
  });
  test(
    'web and mobile share closing references across close expiry and morning',
    () async {
      await login();
      final fixture =
          jsonDecode(
                File(
                  '../tests/fixtures/portfolio/reference_price_parity.json',
                ).readAsStringSync(),
              )
              as Map<String, dynamic>;
      for (final enabled in [false, true]) {
        backend = SupabaseBackend(
          client,
          storage,
          recurringMarketFeed: enabled,
        );
        for (final scenario in fixture['scenarios'] as List) {
          calls.clear();
          respond = (_) async =>
              jsonResponse(jsonEncode(fixture['references']), 200);
          final result = await backend.listDocuments(
            collectionId: 'latest_prices',
          );
          expect(
            calls.single.url.path,
            '/rest/v1/rpc/read_latest_price_references_v1',
          );
          final now = DateTime.parse(scenario['now'] as String);
          final rows = <Map<String, dynamic>>[
            {
              'c_name': 'SGTM',
              '_market_display': {
                'asset_key': 'company:fixture',
                'available': true,
                'price_basis': 'REPORTED_QUOTE',
                'reported_day': scenario['day'],
                'price_decimal': '526',
                'captured_at': scenario['captured'],
                'expires_at': scenario['expires'],
              },
            },
          ];
          final prices = portfolioDisplayPrices(
            result.documents.map((d) => d.data).toList(),
            rows,
            now: now,
          );
          expect(
            prices['SGTM']!.price,
            scenario['expected'],
            reason: scenario['name'] as String,
          );
          expect(prices['SGTM']!.price, isNot(580));
        }
      }
    },
  );
  test(
    'authenticated display selects the explicit recurring reader without financial writes',
    () async {
      await login();
      for (final recurring in [false, true]) {
        backend = SupabaseBackend(
          client,
          storage,
          marketDisplayEnabled: true,
          recurringMarketFeed: recurring,
        );
        calls.clear();
        respond = (_) async => jsonResponse('{}', 200);
        await backend.readMarketDisplay();
        expect(calls, hasLength(1));
        expect(
          calls.single.url.path,
          '/rest/v1/rpc/read_shadow_application_feed${recurring ? '_recurring_v1' : ''}',
        );
        expect(jsonDecode(calls.single.body), isNull);
      }
    },
  );

  test('rejects elevated keys and malformed project URL', () {
    expect(
      () => validateSupabaseConfiguration(fixtureUrl, 'sb_secret_fixture'),
      throwsA(isA<BackendFailure>()),
    );
    expect(
      () => validateSupabaseConfiguration('$fixtureUrl/rest/v1', fixtureKey),
      throwsA(isA<BackendFailure>()),
    );
    validateSupabaseConfiguration(fixtureUrl, fixtureKey);
  });

  test('confirmation signup does not manufacture a session', () async {
    respond = (_) async => jsonResponse(jsonEncode(fixtureUser), 200);
    final outcome = await backend.signUp(
      email: 'fixture@example.invalid',
      password: 'fixture-password',
      name: 'Fixture',
      remember: true,
    );
    expect(outcome, SignUpOutcome.confirmationRequired);
    expect(client.auth.currentSession, isNull);
    expect(await storage.hasAccessToken(), isFalse);
    expect(calls.single.url.path, '/auth/v1/signup');
  });

  test(
    'login persists only when requested and validates user remotely',
    () async {
      await login();
      expect(await storage.hasAccessToken(), isTrue);
      respond = (_) async => jsonResponse(jsonEncode(fixtureUser), 200);
      expect((await backend.restoreUser()).id, 'fixture-user');
      expect(calls.single.url.path, '/auth/v1/user');
      await login(remember: false);
      expect(await storage.hasAccessToken(), isFalse);
      expect(client.auth.currentSession, isNotNull);
    },
  );

  test('expired restored session refreshes before user validation', () async {
    await client.auth.setInitialSession(
      jsonEncode(fixtureSession(expired: true)),
    );
    respond = (request) async => jsonResponse(
      jsonEncode(
        request.url.path.endsWith('/token') ? fixtureSession() : fixtureUser,
      ),
      200,
    );
    expect((await backend.restoreUser()).id, 'fixture-user');
    expect(calls.map((r) => r.url.path), ['/auth/v1/token', '/auth/v1/user']);
  });

  test(
    'history uses bounded pages and stable ordering without losing negative/null ratios',
    () async {
      respond = (request) async {
        final offset = int.parse(request.url.queryParameters['offset'] ?? '0');
        final count = int.parse(request.url.queryParameters['limit']!);
        expect(count, lessThanOrEqualTo(500));
        expect(
          request.url.queryParameters['order'],
          'date.desc.nullslast,id.desc.nullslast',
        );
        expect(request.url.queryParameters['c_name'], 'eq.A,"B\\C');
        expect(
          request.url.queryParameters['select'],
          isNot(contains('source')),
        );
        return jsonResponse(
          jsonEncode(
            List.generate(
              count,
              (i) => {
                'id': 'row-${offset + i}',
                'per': -70.97,
                'pb': null,
                'source': 'private-fixture',
              },
            ),
          ),
          200,
        );
      };
      final result = await backend.listDocuments(
        collectionId: 'data',
        queries: [
          Query.equal('c_name', 'A,"B\\C'),
          Query.orderDesc('date'),
          Query.limit(2000),
        ],
      );
      expect(result.documents.length, 2000);
      expect(calls.length, 4);
      expect(result.documents.first.data['per'], -70.97);
      expect(result.documents.first.data['pb'], isNull);
      expect(result.documents.first.data.containsKey('source'), isFalse);
      expect(result.documents.last.id, 'row-1999');
    },
  );

  test(
    'pagination preserves explicit offset and stops at short final page',
    () async {
      respond = (request) async {
        final offset = int.parse(request.url.queryParameters['offset']!);
        final count = offset == 100 ? 500 : 7;
        return jsonResponse(
          jsonEncode(List.generate(count, (i) => {'id': 'row-${offset + i}'})),
          200,
        );
      };
      final result = await backend.listDocuments(
        collectionId: 'data',
        queries: [Query.limit(1000), Query.offset(100)],
      );
      expect(result.documents.length, 507);
      expect(calls.map((r) => r.url.queryParameters['offset']), ['100', '600']);
    },
  );

  test(
    'private reads require session and use owner RLS with user JWT',
    () async {
      await expectLater(
        backend.listDocuments(collectionId: 'portefeuille'),
        throwsA(isA<BackendFailure>()),
      );
      expect(calls, isEmpty);
      await login();
      respond = (request) async {
        expect(
          request.headers['authorization'],
          'Bearer ${client.auth.currentSession!.accessToken}',
        );
        return jsonResponse(
          '[{"id":"holding","quantity":0.5,"total_cost":40}]',
          200,
        );
      };
      final page = await backend.listDocuments(
        collectionId: 'portefeuille',
        queries: [Query.limit(200)],
      );
      expect(page.documents.single.data['quantity'], 0.5);
    },
  );

  test('unknown collections and fields fail before sending requests', () async {
    for (final collection in [
      'users',
      'migration_stage.documents',
      'portfolio_private.trade_requests',
    ]) {
      await expectLater(
        backend.listDocuments(collectionId: collection),
        throwsA(isA<BackendFailure>()),
      );
    }
    await expectLater(
      backend.listDocuments(
        collectionId: 'data',
        queries: [Query.equal('source', 'fixture')],
      ),
      throwsA(isA<BackendFailure>()),
    );
    await expectLater(
      backend.listDocuments(
        collectionId: 'data',
        queries: [Query.limit(10001)],
      ),
      throwsA(isA<BackendFailure>()),
    );
    expect(calls, isEmpty);
  });

  test(
    'supplemental profiles preserve nested annual, forecast and interim data',
    () async {
      final profile = {
        'charts': {
          'ca': {'2025': 110, '2026p': 120},
        },
        'annual_statements': {
          'ca': {'2025': 110, '2026p': 120, '2027p': null},
        },
        'trim': {'T12026': 30},
        'sem': {'S12026': 50},
      };
      respond = (_) async => jsonResponse(
        jsonEncode([
          {
            'id': 'FIX',
            'c_name': 'Fixture',
            'captured_at': '2026-10-24T12:00:00Z',
            'profile': profile,
            'raw_responses': 'private-fixture',
          },
        ]),
        200,
      );
      final result = await backend.listDocuments(
        collectionId: 'company_profiles',
        queries: [Query.equal('id', 'FIX')],
      );
      expect(result.documents.single.data['profile'], profile);
      expect(
        result.documents.single.data.containsKey('raw_responses'),
        isFalse,
      );
      expect(
        calls.single.url.queryParameters['select'],
        'id,c_name,captured_at,profile',
      );
    },
  );

  test(
    'trade sends one RPC with decimal strings, retry ID and no owner argument',
    () async {
      await login();
      const id = 'a0000000-0000-4000-8000-000000000001';
      respond = (request) async {
        final payload = jsonDecode(request.body) as Map;
        expect(request.method, 'POST');
        expect(request.url.path, '/rest/v1/rpc/record_trade');
        expect(payload.keys.toSet(), {
          'p_request_id',
          'p_side',
          'p_c_name',
          'p_quantity',
          'p_price',
        });
        expect(payload['p_request_id'], id);
        expect(payload['p_quantity'], '2.5');
        expect(payload['p_price'], '100.15');
        return jsonResponse(jsonEncode(id), 200);
      };
      await backend.recordTrade(
        requestId: id,
        isBuy: true,
        company: 'Fixture',
        quantity: '2.5',
        price: '100.15',
      );
      expect(calls.length, 1);
    },
  );

  test(
    'saved recovery precedes trades and sends no owner or email argument',
    () async {
      await login();
      backend = SupabaseBackend(
        client,
        storage,
        portfolioRecoveryEnabled: true,
      );
      const id = 'a0000000-0000-4000-8000-000000000001';
      respond = (request) async {
        if (request.url.path.endsWith('/claim_saved_portfolio')) {
          expect(jsonDecode(request.body), isEmpty);
          return jsonResponse(
            '{"status":"CLAIMED","counts":{"achats":1,"ventes":0,"portefeuille":1,"benefits":0}}',
            200,
          );
        }
        expect(request.url.path, '/rest/v1/rpc/record_trade');
        return jsonResponse(jsonEncode(id), 200);
      };
      for (var i = 0; i < 2; i++) {
        await backend.recordTrade(
          requestId: id,
          isBuy: true,
          company: 'Fixture',
          quantity: '1',
          price: '10',
        );
      }
      expect(calls.map((r) => r.url.path), [
        '/rest/v1/rpc/claim_saved_portfolio',
        '/rest/v1/rpc/record_trade',
        '/rest/v1/rpc/record_trade',
      ]);
    },
  );

  test(
    'unresolved recovery prevents trading and password proof has a clear message',
    () async {
      await login();
      backend = SupabaseBackend(
        client,
        storage,
        portfolioRecoveryEnabled: true,
      );
      for (final status in ['REVIEW_REQUIRED', 'PASSWORD_REQUIRED']) {
        calls.clear();
        respond = (_) async =>
            jsonResponse(jsonEncode({'status': status}), 200);
        await expectLater(
          backend.recordTrade(
            requestId: 'a0000000-0000-4000-8000-000000000001',
            isBuy: true,
            company: 'Fixture',
            quantity: '1',
            price: '10',
          ),
          throwsA(isA<BackendFailure>()),
        );
        expect(calls.single.url.path, '/rest/v1/rpc/claim_saved_portfolio');
      }
    },
  );

  test(
    'remote Auth and database diagnostics never reach UI exceptions',
    () async {
      respond = (_) async => jsonResponse(
        '{"code":"invalid_credentials","msg":"fixture-secret-diagnostic"}',
        400,
      );
      await expectLater(
        backend.signIn(
          email: 'fixture@example.invalid',
          password: 'fixture-password',
          remember: true,
        ),
        throwsA(
          predicate(
            (e) => e is BackendFailure && !e.message.contains('fixture-secret'),
          ),
        ),
      );
      respond = (_) async => jsonResponse(
        '{"message":"fixture-secret-diagnostic","code":"42501"}',
        403,
      );
      await expectLater(
        backend.listDocuments(collectionId: 'data'),
        throwsA(
          predicate(
            (e) => e is BackendFailure && !e.message.contains('fixture-secret'),
          ),
        ),
      );
    },
  );

  test(
    'logout removes local and persisted credentials even when revocation fails',
    () async {
      await login();
      respond = (_) async =>
          jsonResponse('{"msg":"fixture-secret-diagnostic"}', 503);
      await expectLater(
        backend.signOut(),
        throwsA(predicate((e) => e is BackendFailure && e.signedOut)),
      );
      expect(client.auth.currentSession, isNull);
      expect(await storage.hasAccessToken(), isFalse);
      expect(await storage.storage.read(key: storage.sessionKey), isNull);
    },
  );
}
