import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:myinterpreter_app/shadow_market_feed.dart';

void main() {
  // The fixture is produced from the live database by
  // migrations/supabase/20261121_public_application_feed.sql, so this test
  // fails if the SQL shape and the app parser drift apart.
  test('the public market feed satisfies the preview contract', () {
    final payload = jsonDecode(
      File('../tests/fixtures/public_feed_sample.json').readAsStringSync(),
    );
    final snapshot = ShadowMarketSnapshot.fromJson(payload);

    expect(snapshot.status, 'AVAILABLE');
    expect(snapshot.rows, hasLength(3));

    final fresh = snapshot.rows.firstWhere(
      (row) => row.status == 'REPORTED_DATE_ONLY',
    );
    expect(fresh.priceAt(fresh.capturedAt!), isNotNull);

    final stale = snapshot.rows.firstWhere(
      (row) => row.status == 'MISSING_QUOTE',
    );
    expect(stale.priceAt(stale.capturedAt ?? DateTime.now()), isNull);

    final index = snapshot.rows.firstWhere(
      (row) => row.instrumentType == 'INDEX',
    );
    expect(index.name, 'MASI');
    expect(index.priceAt(index.capturedAt!), isNotNull);
  });
}
