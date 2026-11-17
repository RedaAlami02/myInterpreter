// Explicit integration test only; excluded from default *_test.dart discovery.
// tools/check_supabase_mobile.py provides a private temporary fixture and cleans
// up its synthetic accounts. Never place real credentials in this source file.
import 'dart:convert';
import 'dart:io';

import 'package:myinterpreter_app/query.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:myinterpreter_app/backend_contract.dart';
import 'package:myinterpreter_app/secure_session_storage.dart';
import 'package:myinterpreter_app/supabase_backend.dart';
import 'package:myinterpreter_app/trade_submission.dart';

class NetworkBinding extends AutomatedTestWidgetsFlutterBinding {
  @override
  bool get overrideHttpClient => false;
}

void main() {
  NetworkBinding();
  final fixturePath = Platform.environment['MYINTERPRETER_LIVE_FIXTURE'];
  test(
    'live mobile SDK login, privacy, trades, refresh, restore and logout',
    () async {
      final fixture =
          jsonDecode(File(fixturePath!).readAsStringSync())
              as Map<String, dynamic>;
      final progress = File('${File(fixturePath).parent.path}/progress.json');
      void phase(String name) =>
          progress.writeAsStringSync(jsonEncode({'phase': name}));
      void require(bool condition) => expect(condition, isTrue);
      phase('initialize');
      FlutterSecureStorage.setMockInitialValues({});
      validateSupabaseConfiguration(
        fixture['url'] as String,
        fixture['publishable_key'] as String,
      );
      final storage = SecureSessionStorage('live-fixture-a');
      await Supabase.initialize(
        url: fixture['url'] as String,
        publishableKey: fixture['publishable_key'] as String,
        debug: false,
        authOptions: FlutterAuthClientOptions(
          localStorage: storage,
          pkceAsyncStorage: SecurePkceStorage('live-fixture-a'),
          detectSessionInUri: false,
        ),
      );
      final first = SupabaseBackend(Supabase.instance.client, storage);
      final secondClient = SupabaseClient(
        fixture['url'] as String,
        fixture['publishable_key'] as String,
        authOptions: const AuthClientOptions(autoRefreshToken: false),
      );
      final second = SupabaseBackend(
        secondClient,
        SecureSessionStorage('live-fixture-b'),
      );
      final restoredClient = SupabaseClient(
        fixture['url'] as String,
        fixture['publishable_key'] as String,
        authOptions: const AuthClientOptions(autoRefreshToken: false),
      );
      try {
        phase('anonymous_market_and_portfolio_denied');
        for (final table in ['company', 'data', 'portefeuille']) {
          var anonymousDenied = false;
          try {
            await first.listDocuments(collectionId: table);
          } on BackendFailure {
            anonymousDenied = true;
          }
          require(anonymousDenied);
        }

        phase('login_and_empty_account');
        final identities = fixture['identities'] as List;
        await first.signIn(
          email: identities[0]['email'] as String,
          password: fixture['password'] as String,
          remember: true,
        );
        require((await first.getUser()).id == identities[0]['id']);
        require(
          (await first.listDocuments(
            collectionId: 'portefeuille',
          )).documents.isEmpty,
        );
        require(await storage.hasAccessToken());

        phase('authenticated_market_and_pagination');
        require(
          (await first.listDocuments(
            collectionId: 'company',
            queries: [Query.limit(500)],
          )).documents.isNotEmpty,
        );
        final history = await first.listDocuments(
          collectionId: 'data',
          queries: [Query.orderDesc('date'), Query.limit(1501)],
        );
        require(history.documents.length == 1501);
        require(history.documents.map((d) => d.id).toSet().length == 1501);

        phase('buy_retry');
        final buy = TradeSubmission(
          isBuy: true,
          company: fixture['company'] as String,
          quantity: '2',
          price: '100.15',
        );
        await buy.submit(first);
        await buy.submit(first);
        final holdings = (await first.listDocuments(
          collectionId: 'portefeuille',
        )).documents;
        require(holdings.length == 1);
        require((holdings.single.data['quantity'] as num).toDouble() == 2);
        require(
          ((holdings.single.data['total_cost'] as num).toDouble() - 200.30)
                  .abs() <
              1e-8,
        );
        require(
          (await first.listDocuments(
                collectionId: 'achats',
              )).documents.length ==
              1,
        );

        phase('cross_owner_privacy');
        await second.signIn(
          email: identities[1]['email'] as String,
          password: fixture['password'] as String,
          remember: false,
        );
        require((await second.getUser()).id == identities[1]['id']);
        for (final table in ['achats', 'ventes', 'portefeuille', 'benefits']) {
          require(
            (await second.listDocuments(collectionId: table)).documents.isEmpty,
          );
          require(
            (await second.listDocuments(
              collectionId: table,
              queries: [Query.equal('user_id', identities[0]['id'])],
            )).documents.isEmpty,
          );
        }

        phase('partial_and_full_sale');
        await TradeSubmission(
          isBuy: false,
          company: fixture['company'] as String,
          quantity: '0.5',
          price: '120',
        ).submit(first);
        final remaining = (await first.listDocuments(
          collectionId: 'portefeuille',
        )).documents.single;
        require((remaining.data['quantity'] as num).toDouble() == 1.5);
        require(
          ((remaining.data['total_cost'] as num).toDouble() - 150.225).abs() <
              1e-8,
        );
        final sale = TradeSubmission(
          isBuy: false,
          company: fixture['company'] as String,
          quantity: '1.5',
          price: '120',
        );
        await sale.submit(first);
        await sale.submit(first);
        require(
          (await first.listDocuments(
            collectionId: 'portefeuille',
          )).documents.isEmpty,
        );
        require(
          (await first.listDocuments(
                collectionId: 'ventes',
              )).documents.length ==
              2,
        );

        phase('refresh_and_persisted_restore');
        await first.client.auth.refreshSession();
        require((await first.getUser()).id == identities[0]['id']);
        await Future<void>.delayed(const Duration(milliseconds: 100));
        final persisted = await SecureSessionStorage(
          'live-fixture-a',
        ).accessToken();
        require(persisted != null);
        await restoredClient.auth.recoverSession(persisted!);
        final restored = SupabaseBackend(
          restoredClient,
          SecureSessionStorage('live-fixture-a'),
        );
        require((await restored.restoreUser()).id == identities[0]['id']);

        phase('logout');
        await first.signOut();
        require(first.client.auth.currentSession == null);
        require(!await storage.hasAccessToken());
        await second.signOut();
        phase('passed');
      } finally {
        await secondClient.dispose();
        await restoredClient.dispose();
        await Supabase.instance.dispose();
      }
    },
    skip: fixturePath == null
        ? 'Run with tools/check_supabase_mobile.py'
        : false,
  );
}
