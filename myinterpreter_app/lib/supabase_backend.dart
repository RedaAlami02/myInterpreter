import 'dart:convert';
import 'dart:math';

import 'package:supabase_flutter/supabase_flutter.dart';

import 'backend_contract.dart';
import 'market_columns.dart';
import 'mobile_email_auth.dart';
import 'secure_session_storage.dart';

const _privateColumns = <String, List<String>>{
  'achats': ['id', 'user_id', 'c_name', 'number', 'prix_achat', 'date'],
  'ventes': ['id', 'user_id', 'c_name', 'number', 'prix_vente', 'date'],
  'portefeuille': ['id', 'user_id', 'c_name', 'quantity', 'total_cost'],
  'benefits': ['id', 'user_id', 'date', 'value'],
};

/// Only public configuration is accepted, including in tests and build defines.
void validateSupabaseConfiguration(String url, String key) {
  if (!RegExp(r'^https://[a-z0-9]{10,40}\.supabase\.co/?$').hasMatch(url) ||
      !RegExp(r'^sb_publishable_[A-Za-z0-9_-]+$').hasMatch(key)) {
    throw const BackendFailure('Invalid public backend configuration.');
  }
}

class SupabaseBackend
    implements AppBackend, EmailAuthBackend, MarketDisplayBackend {
  final SupabaseClient client;
  final SecureSessionStorage sessionStorage;
  final MobileEmailAuth emailAuth;
  final bool portfolioRecoveryEnabled;
  String? _recoveredUser;
  String? _claimingUser;
  Future<void>? _claimInFlight;
  @override
  final bool marketDisplayEnabled;
  final bool recurringMarketFeed;
  SupabaseBackend(
    this.client,
    this.sessionStorage, {
    bool emailLinksEnabled = false,
    this.marketDisplayEnabled = false,
    this.recurringMarketFeed = false,
    this.portfolioRecoveryEnabled = false,
    DateTime Function()? clock,
  }) : emailAuth = MobileEmailAuth(
         client,
         sessionStorage,
         enabled: emailLinksEnabled,
         clock: clock,
       );

  @override
  Future<Object?> readMarketDisplay() async {
    _requireNormalSession();
    if (!marketDisplayEnabled) {
      throw const BackendFailure('Market preview is disabled.');
    }
    if (client.auth.currentSession == null) {
      throw const BackendFailure('Please sign in to view market data.');
    }
    try {
      return await client.rpc(
        recurringMarketFeed
            ? 'read_shadow_application_feed_recurring_v1'
            : 'read_shadow_application_feed',
      );
    } catch (_) {
      throw const BackendFailure(
        'Les cours récents sont indisponibles. Réessayez plus tard.',
      );
    }
  }

  @override
  bool get emailLinksEnabled => emailAuth.enabled;
  @override
  bool get hasRecoverySession => emailAuth.hasRecoverySession;
  @override
  Future<void> requestPasswordReset(String email) =>
      emailAuth.requestPasswordReset(email);
  @override
  Future<void> resendConfirmation(String email) =>
      emailAuth.resendConfirmation(email);
  @override
  Future<EmailLinkOutcome> completeEmailLink(Uri uri) =>
      emailAuth.complete(uri);
  @override
  Future<void> updateRecoveredPassword(String password) =>
      emailAuth.updatePassword(password);
  @override
  Future<void> cancelEmailRecovery() => emailAuth.cancel();

  void _requireNormalSession() {
    if (emailAuth.blocksApplication) {
      throw const BackendFailure('Finish or cancel password recovery first.');
    }
  }

  Future<void> _ensurePortfolioRecovery() async {
    if (!portfolioRecoveryEnabled) return;
    final owner = client.auth.currentUser?.id;
    if (owner == null) throw const BackendFailure('Please sign in again.');
    if (_recoveredUser == owner) return;
    if (_claimingUser == owner && _claimInFlight != null) {
      return _claimInFlight!;
    }
    _claimingUser = owner;
    final pending = _claimPortfolio(owner);
    _claimInFlight = pending;
    try {
      await pending;
    } finally {
      if (_claimingUser == owner) {
        _claimInFlight = null;
        _claimingUser = null;
      }
    }
  }

  Future<void> _claimPortfolio(String owner) async {
    try {
      final result = await client.rpc(
        'claim_saved_portfolio',
        params: const <String, dynamic>{},
      );
      if (client.auth.currentUser?.id != owner) {
        throw const BackendFailure('Please sign in again.');
      }
      if (result is Map && result['status'] == 'PASSWORD_REQUIRED') {
        throw const BackendFailure(
          'Sign out and sign in with your password to recover the saved portfolio.',
        );
      }
      if (result is Map &&
          result.length == 1 &&
          ['DISABLED', 'NOT_AVAILABLE'].contains(result['status'])) {
        return;
      }
      final counts = result is Map ? result['counts'] : null;
      if (result is Map &&
          result.length == 2 &&
          result['status'] == 'CLAIMED' &&
          counts is Map &&
          counts.keys.toSet().difference({
            'achats',
            'ventes',
            'portefeuille',
            'benefits',
          }).isEmpty &&
          counts.length == 4 &&
          counts.values.every(
            (value) => value is int && value >= 0 && value <= 10000,
          )) {
        final total = counts.values.cast<int>().fold(0, (a, b) => a + b);
        if (total > 0 && total <= 10000) {
          _recoveredUser = owner;
          return;
        }
      }
      throw const BackendFailure(
        'Saved portfolio recovery needs review before changing holdings.',
      );
    } on BackendFailure {
      rethrow;
    } catch (_) {
      throw const BackendFailure(
        'Saved portfolio recovery could not be verified. Please retry.',
      );
    }
  }

  @override
  Future<AppUser> restoreUser() => getUser();

  @override
  Future<AppUser> getUser() async {
    _requireNormalSession();
    try {
      final session = client.auth.currentSession;
      if (session == null) throw const BackendFailure('Please sign in again.');
      if (session.isExpired) await client.auth.refreshSession();
      final user = (await client.auth.getUser()).user;
      if (user == null) throw const BackendFailure('Please sign in again.');
      return AppUser(id: user.id, email: user.email ?? '');
    } on AuthException catch (error) {
      throw _authFailure(error);
    } on BackendFailure {
      rethrow;
    } catch (_) {
      throw const BackendFailure(
        'Authentication service is temporarily unavailable.',
      );
    }
  }

  @override
  Future<void> signIn({
    required String email,
    required String password,
    required bool remember,
  }) => emailLinksEnabled
      ? emailAuth.passwordSignIn(
          () => _passwordSignIn(
            email: email,
            password: password,
            remember: remember,
          ),
        )
      : _passwordSignIn(email: email, password: password, remember: remember);

  Future<void> _passwordSignIn({
    required String email,
    required String password,
    required bool remember,
  }) async {
    try {
      await sessionStorage.setRemember(remember);
      final result = await client.auth.signInWithPassword(
        email: email,
        password: password,
      );
      if (result.session == null) {
        throw const BackendFailure('Please sign in again.');
      }
      await _persistSession();
    } on AuthException catch (error) {
      throw _authFailure(error);
    } on BackendFailure {
      rethrow;
    } catch (_) {
      throw const BackendFailure('Sign in is temporarily unavailable.');
    }
  }

  @override
  Future<SignUpOutcome> signUp({
    required String email,
    required String password,
    required String name,
    required bool remember,
  }) async {
    if (emailLinksEnabled) {
      return emailAuth.signUp(
        email: email,
        password: password,
        name: name,
        remember: remember,
      );
    }
    try {
      await sessionStorage.setRemember(remember);
      final result = await client.auth.signUp(
        email: email,
        password: password,
        data: {'name': name},
      );
      if (result.session == null) return SignUpOutcome.confirmationRequired;
      await _persistSession();
      return SignUpOutcome.signedIn;
    } on AuthException catch (error) {
      throw _authFailure(error);
    } catch (_) {
      throw const BackendFailure('Sign up is temporarily unavailable.');
    }
  }

  Future<void> _persistSession() async {
    final session = client.auth.currentSession;
    if (session != null) {
      await sessionStorage.persistSession(jsonEncode(session.toJson()));
    }
  }

  @override
  Future<void> signOut() async {
    if (emailLinksEnabled) {
      await emailAuth.cancel();
      return;
    }
    var revocationFailed = false;
    try {
      // SDK removes its in-memory session before attempting remote revocation.
      await client.auth.signOut(scope: SignOutScope.local);
    } catch (_) {
      revocationFailed = true;
    }
    try {
      await sessionStorage.setRemember(false);
    } catch (_) {
      throw const BackendFailure(
        'Local sign-out cleanup failed. Please retry before closing this app.',
      );
    }
    if (revocationFailed) {
      throw const BackendFailure(
        'Signed out on this device. Server revocation could not be confirmed.',
        signedOut: true,
      );
    }
  }

  @override
  Future<DocumentPage> listDocuments({
    required String collectionId,
    List<String> queries = const [],
  }) async {
    _requireNormalSession();
    final fields =
        publicMarketColumns[collectionId] ?? _privateColumns[collectionId];
    if (fields == null) {
      throw const BackendFailure('Unsupported data collection.');
    }
    if (_privateColumns.containsKey(collectionId) &&
        client.auth.currentSession == null) {
      throw const BackendFailure('Please sign in again.');
    }
    try {
      final plan = _ReadPlan(fields, queries);
      if (_privateColumns.containsKey(collectionId)) {
        await _ensurePortfolioRecovery();
      }
      final rows = <AppDocument>[];
      while (rows.length < plan.limit) {
        final count = min(500, plan.limit - rows.length);
        var filter = client.from(collectionId).select(fields.join(','));
        for (final entry in plan.filters) {
          filter = switch (entry.method) {
            'equal' =>
              entry.value == null
                  ? filter.isFilter(entry.field, null)
                  : filter.eq(entry.field, entry.value!),
            'greaterThan' => filter.gt(entry.field, entry.value!),
            'greaterThanEqual' => filter.gte(entry.field, entry.value!),
            _ => throw const BackendFailure('Unsupported data filter.'),
          };
        }
        PostgrestTransformBuilder<List<Map<String, dynamic>>> request = filter;
        for (final entry in plan.orders.entries) {
          request = request.order(entry.key, ascending: entry.value);
        }
        final offset = plan.offset + rows.length;
        final page = await request.range(offset, offset + count - 1);
        for (final row in page) {
          final id = row['id'];
          if (id is! String || id.isEmpty) {
            throw const BackendFailure('Invalid data response.');
          }
          // Strip identity and unexpected response columns before screens see them.
          rows.add(
            AppDocument(
              id: id,
              data: {
                for (final field in fields)
                  if (field != 'id') field: row[field],
              },
            ),
          );
        }
        if (page.length < count) break;
      }
      if (rows.map((row) => row.id).toSet().length != rows.length) {
        throw const BackendFailure(
          'Data changed during loading. Please retry.',
        );
      }
      return DocumentPage(rows);
    } on BackendFailure {
      rethrow;
    } catch (_) {
      throw const BackendFailure('Data could not be loaded. Please retry.');
    }
  }

  @override
  Future<void> recordTrade({
    required String requestId,
    required bool isBuy,
    required String company,
    required String quantity,
    required String price,
  }) async {
    _requireNormalSession();
    if (client.auth.currentSession == null) {
      throw const BackendFailure('Please sign in again.');
    }
    try {
      await _ensurePortfolioRecovery();
      final receipt = await client.rpc(
        'record_trade',
        params: {
          'p_request_id': requestId,
          'p_side': isBuy ? 'buy' : 'sell',
          'p_c_name': company,
          // Preserve the entered decimal strings. Never send a caller-provided owner.
          'p_quantity': quantity, 'p_price': price,
        },
      );
      if (receipt != requestId) {
        throw const BackendFailure('Trade receipt could not be verified.');
      }
    } on BackendFailure {
      rethrow;
    } catch (_) {
      throw const BackendFailure(
        'Trade could not be confirmed. Check your holdings and inputs, then retry the same submission.',
      );
    }
  }
}

BackendFailure _authFailure(AuthException error) {
  return switch (error.code) {
    'email_not_confirmed' => const BackendFailure(
      'Confirm your email address before signing in.',
    ),
    'invalid_credentials' => const BackendFailure(
      'Check your email and password.',
    ),
    'over_request_rate_limit' || 'over_email_send_rate_limit' =>
      const BackendFailure('Too many attempts. Please wait and retry.'),
    _ => const BackendFailure(
      'Authentication could not be completed. Check your details and retry.',
    ),
  };
}

class _Filter {
  final String field;
  final String method;
  final Object? value;
  _Filter(this.field, this.method, this.value);
}

class _ReadPlan {
  int limit = 100;
  int offset = 0;
  final filters = <_Filter>[];
  final orders = <String, bool>{};
  _ReadPlan(List<String> fields, List<String> queries) {
    for (final encoded in queries) {
      final query = jsonDecode(encoded) as Map<String, dynamic>;
      final method = query['method'];
      final values = query['values'] as List<dynamic>? ?? [];
      if (method == 'limit' || method == 'offset') {
        if (values.length != 1 || values.first is! int) {
          throw const BackendFailure('Invalid data pagination.');
        }
        final value = values.first as int;
        if (value < (method == 'limit' ? 1 : 0) ||
            value > (method == 'limit' ? 10000 : 10000000)) {
          throw const BackendFailure('Invalid data pagination.');
        }
        if (method == 'limit') {
          limit = value;
        } else {
          offset = value;
        }
        continue;
      }
      final field = query['attribute'] == r'$id' ? 'id' : query['attribute'];
      if (!fields.contains(field)) {
        throw const BackendFailure('Unsupported data field.');
      }
      if (method == 'orderAsc' || method == 'orderDesc') {
        orders[field as String] = method == 'orderAsc';
      } else if ([
            'equal',
            'greaterThan',
            'greaterThanEqual',
          ].contains(method) &&
          values.length == 1 &&
          (values.first == null ||
              values.first is String ||
              values.first is num ||
              values.first is bool) &&
          !(values.first == null && method != 'equal') &&
          !filters.any((entry) => entry.field == field)) {
        filters.add(_Filter(field as String, method as String, values.first));
      } else {
        throw const BackendFailure('Unsupported data query.');
      }
    }
    orders.putIfAbsent('id', () => false);
  }
}
