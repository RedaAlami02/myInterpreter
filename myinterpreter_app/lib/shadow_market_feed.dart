import 'package:supabase_flutter/supabase_flutter.dart';
import 'backend_contract.dart';

DateTime? _previewTime(Object? value) {
  if (value == null) return null;
  if (value is! String ||
      !RegExp(
        r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$',
      ).hasMatch(value)) {
    throw const BackendFailure('Invalid market preview timestamp.');
  }
  final year = int.parse(value.substring(0, 4));
  final month = int.parse(value.substring(5, 7));
  final day = int.parse(value.substring(8, 10));
  final calendar = DateTime.utc(year, month, day);
  final stamp = DateTime.tryParse(value);
  if (stamp == null ||
      calendar.year != year ||
      calendar.month != month ||
      calendar.day != day ||
      int.parse(value.substring(11, 13)) > 23 ||
      int.parse(value.substring(14, 16)) > 59 ||
      int.parse(value.substring(17, 19)) > 59) {
    throw const BackendFailure('Invalid market preview timestamp.');
  }
  return stamp.toUtc();
}

bool _validPreviewPrice(Object? value) {
  if (value is! String ||
      !RegExp(r'^[0-9]{1,13}(?:\.[0-9]{1,28})?$').hasMatch(value) ||
      value.replaceAll(RegExp(r'[0.]'), '').isEmpty) {
    return false;
  }
  final parts = value.split('.');
  final integer = BigInt.parse(parts.first),
      maximum = BigInt.parse('1000000000000');
  return integer < maximum ||
      (integer == maximum &&
          (parts.length == 1 || parts[1].replaceAll('0', '').isEmpty));
}

class ReferencePrice {
  final String price;
  final DateTime capturedAt, expiresAt;
  ReferencePrice._(this.price, this.capturedAt, this.expiresAt);

  factory ReferencePrice.fromJson(
    Map<String, dynamic> value,
    DateTime? feedCapture,
  ) {
    if (!_validPreviewPrice(value['price_decimal']) ||
        value['price_basis'] != 'INSTRUMENT_REFERENCE' ||
        !value.containsKey('source_event_at') ||
        value['source_event_at'] != null ||
        !value.containsKey('reported_day') ||
        value['reported_day'] != null ||
        value['reported_time_timezone'] != 'UNKNOWN' ||
        value['prediction_eligible'] != false ||
        value['portfolio_valuation_eligible'] != false) {
      throw const BackendFailure('Invalid reference price.');
    }
    final capture = _previewTime(value['captured_at']),
        expiry = _previewTime(value['expires_at']);
    if (capture == null ||
        expiry == null ||
        feedCapture == null ||
        capture != feedCapture ||
        !expiry.isAfter(capture) ||
        expiry.difference(capture) > const Duration(hours: 1)) {
      throw const BackendFailure('Invalid reference-price lifetime.');
    }
    return ReferencePrice._(value['price_decimal'] as String, capture, expiry);
  }

  String? priceAt(DateTime asOf) =>
      !asOf.isBefore(capturedAt) && asOf.isBefore(expiresAt) ? price : null;
}

class ShadowQuote {
  final String assetKey, name, symbol, instrumentType, status;
  final String? reportedTimeText;
  final DateTime? capturedAt, expiresAt;
  final String? _price;
  final ReferencePrice? referencePrice;
  final bool referenceConflict;
  final Map<String, dynamic>? _applicationFields;
  final DateTime? _applicationExpiry;
  final DateTime? _applicationSourceEvent;
  final String? _applicationReportedDay;
  ShadowQuote._(
    this.assetKey,
    this.name,
    this.symbol,
    this.instrumentType,
    this.status,
    this.reportedTimeText,
    this.capturedAt,
    this.expiresAt,
    this._price,
    this.referencePrice,
    this.referenceConflict,
    this._applicationFields,
    this._applicationExpiry,
    this._applicationSourceEvent,
    this._applicationReportedDay,
  );

  factory ShadowQuote.fromJson(
    Map<String, dynamic> row, {
    bool withReferences = false,
    bool withApplication = false,
    DateTime? feedCapture,
  }) {
    const statuses = {
      'MISSING_QUOTE',
      'CONFLICTING_QUOTES',
      'STALE_OR_MISSING_SOURCE_DATE',
      'STALE_CAPTURE_DATE',
      'STALE_CAPTURE',
      'STALE_SOURCE_EVENT',
      'FUTURE_CAPTURE',
      'REPORTED_DATE_ONLY',
      'REPORTED_EVENT_VERIFIED',
    };
    if (row['asset_key'] is! String ||
        row['c_name'] is! String ||
        row['symbol'] is! String ||
        !{'STOCK', 'INDEX'}.contains(row['instrument_type']) ||
        !statuses.contains(row['status']) ||
        row['price_basis'] != 'REPORTED_QUOTE' ||
        row['prediction_eligible'] != false ||
        row['portfolio_valuation_eligible'] != false ||
        row['reported_time_timezone'] != 'UNKNOWN') {
      throw const BackendFailure('Invalid market preview row.');
    }
    final capture = _previewTime(row['captured_at']),
        expiry = _previewTime(row['expires_at']);
    final price = row['price_decimal'];
    final current = {
      'REPORTED_DATE_ONLY',
      'REPORTED_EVENT_VERIFIED',
    }.contains(row['status']);
    if (current) {
      if (!_validPreviewPrice(price) ||
          capture == null ||
          expiry == null ||
          !expiry.isAfter(capture) ||
          expiry.difference(capture) > const Duration(hours: 1)) {
        throw const BackendFailure('Invalid market preview price.');
      }
    } else if (price != null || expiry != null) {
      throw const BackendFailure('Unavailable market preview price.');
    }
    ReferencePrice? reference;
    if (withReferences) {
      if (row['reference_conflict'] is! bool ||
          (row['reference_conflict'] == true &&
              (row['status'] != 'MISSING_QUOTE' ||
                  row['instrument_type'] != 'STOCK' ||
                  row['reference_price'] != null))) {
        throw const BackendFailure('Invalid reference conflict flag.');
      }
      if (!row.containsKey('reference_price')) {
        throw const BackendFailure('Missing reference-price field.');
      }
      if (row['reference_price'] != null) {
        if (row['status'] != 'MISSING_QUOTE' ||
            row['instrument_type'] != 'STOCK' ||
            row['reference_price'] is! Map<String, dynamic>) {
          throw const BackendFailure('Invalid reference price.');
        }
        reference = ReferencePrice.fromJson(
          row['reference_price'],
          feedCapture,
        );
      }
    }
    Map<String, dynamic>? application;
    DateTime? applicationExpiry;
    DateTime? applicationSourceEvent;
    String? applicationReportedDay;
    if (withApplication) {
      if (!row.containsKey('application_fields') ||
          !row.containsKey('application_expires_at')) {
        throw const BackendFailure('Missing application display fields.');
      }
      applicationExpiry = _previewTime(row['application_expires_at']);
      final fields = row['application_fields'];
      if (fields == null) {
        if (applicationExpiry != null) {
          throw const BackendFailure('Unavailable application expiry.');
        }
      } else {
        applicationSourceEvent = _previewTime(row['source_event_at']);
        final day = row['reported_day'];
        if (day != null) {
          if (day is! String ||
              !RegExp(r'^\d{4}-\d{2}-\d{2}$').hasMatch(day) ||
              _previewTime(
                    '${day}T00:00:00Z',
                  )!.toIso8601String().substring(0, 10) !=
                  day) {
            throw const BackendFailure('Invalid application reported date.');
          }
          applicationReportedDay = day;
        }
        final chosenPrice = price ?? reference?.price;
        final chosenCapture = price != null ? capture : reference?.capturedAt;
        final chosenExpiry = price != null ? expiry : reference?.expiresAt;
        if (fields is! Map<String, dynamic> ||
            chosenPrice == null ||
            chosenCapture == null ||
            chosenExpiry == null ||
            applicationExpiry == null ||
            !applicationExpiry.isAfter(chosenCapture) ||
            applicationExpiry.isAfter(chosenExpiry) ||
            fields['c_name'] != row['c_name'] ||
            _previewTime(fields['date']) != chosenCapture ||
            fields['pa'] is! num ||
            !(fields['pa'] as num).isFinite ||
            (fields['pa'] as num).toDouble() !=
                double.parse(chosenPrice as String) ||
            (row['instrument_type'] == 'STOCK' &&
                fields['symbol'] != row['symbol'])) {
          throw const BackendFailure('Invalid application display row.');
        }
        const allowed = {
          'date',
          'c_name',
          'symbol',
          'pa',
          'cb',
          'pb',
          'per',
          'peg',
          'pr',
          'per_rating',
          'pb_rating',
          'peg_rating',
          'pr_rating',
          'variation',
          'variation_v',
          'cours_ref',
          'open_price',
          'high',
          'low',
          'volume',
          'qty_traded',
          'market_cap',
          'data_chart',
        };
        final safe = <String, dynamic>{};
        for (final entry in fields.entries.where(
          (entry) => allowed.contains(entry.key),
        )) {
          final key = entry.key, value = entry.value;
          if (row['instrument_type'] == 'INDEX' &&
              {
                'symbol',
                'cb',
                'pb',
                'per',
                'peg',
                'pr',
                'per_rating',
                'pb_rating',
                'peg_rating',
                'pr_rating',
              }.contains(key)) {
            throw const BackendFailure('Invalid index application field.');
          }
          if (!{'date', 'c_name', 'symbol'}.contains(key)) {
            if (key == 'data_chart') {
              if (value is! String || value.length > 195) {
                throw const BackendFailure('Invalid application chart.');
              }
            } else if (key.endsWith('_rating')) {
              if (!{'green', 'orange', 'red'}.contains(value)) {
                throw const BackendFailure('Invalid application rating.');
              }
            } else if (value is! num ||
                !value.isFinite ||
                value.abs() > 1e30 ||
                (key == 'qty_traded' && (value is! int || value < 0))) {
              throw const BackendFailure('Invalid application number.');
            }
          }
          safe[key] = value;
        }
        application = Map.unmodifiable(safe);
      }
    }
    return ShadowQuote._(
      row['asset_key'],
      row['c_name'],
      row['symbol'],
      row['instrument_type'],
      row['status'],
      row['reported_time_text'] is String ? row['reported_time_text'] : null,
      capture,
      expiry,
      price as String?,
      reference,
      withReferences && row['reference_conflict'] == true,
      application,
      applicationExpiry,
      applicationSourceEvent,
      applicationReportedDay,
    );
  }

  String? priceAt(DateTime asOf) =>
      _price != null && !asOf.isBefore(capturedAt!) && asOf.isBefore(expiresAt!)
      ? _price
      : null;

  DateTime? get applicationExpiresAt => _applicationExpiry;

  /// Current display output only. It is not a historical or valuation document.
  Map<String, dynamic>? applicationRowAt(DateTime asOf) {
    if (_applicationFields == null ||
        _applicationExpiry == null ||
        !asOf.isBefore(_applicationExpiry)) {
      return null;
    }
    final quote = priceAt(asOf), reference = referencePrice?.priceAt(asOf);
    if (quote == null && reference == null) return null;
    return Map.unmodifiable({
      'asset_key': assetKey,
      'fields': _applicationFields,
      'price_decimal': quote ?? reference,
      'price_basis': quote != null ? 'REPORTED_QUOTE' : 'INSTRUMENT_REFERENCE',
      'captured_at': (quote != null ? capturedAt : referencePrice!.capturedAt)!
          .toIso8601String(),
      'expires_at': _applicationExpiry.toIso8601String(),
      'source_event_at': quote != null
          ? _applicationSourceEvent?.toIso8601String()
          : null,
      'reported_day': quote != null ? _applicationReportedDay : null,
      'prediction_eligible': false,
      'portfolio_valuation_eligible': false,
    });
  }

  String? _savedPriceAt(DateTime asOf, AppDocument? document) {
    if (referenceConflict ||
        status != 'MISSING_QUOTE' ||
        instrumentType != 'STOCK' ||
        document == null ||
        document.id.isEmpty ||
        document.data['c_name'] != name ||
        (document.data['symbol'] != null &&
            document.data['symbol'] != '' &&
            document.data['symbol'] != symbol)) {
      return null;
    }
    try {
      final recorded = _previewTime(document.data['date']);
      final value = document.data['pa'];
      final price = value is num && value.isFinite ? value.toString() : value;
      return recorded != null &&
              !recorded.isAfter(asOf) &&
              _validPreviewPrice(price)
          ? price as String
          : null;
    } on BackendFailure {
      return null;
    }
  }

  String? displayPriceAt(DateTime asOf, {AppDocument? lastKnown}) =>
      priceAt(asOf) ??
      referencePrice?.priceAt(asOf) ??
      _savedPriceAt(asOf, lastKnown);
  String displayPriceBasisAt(DateTime asOf, {AppDocument? lastKnown}) =>
      priceAt(asOf) != null
      ? 'REPORTED_QUOTE'
      : referencePrice?.priceAt(asOf) != null
      ? 'INSTRUMENT_REFERENCE'
      : referenceConflict
      ? 'CONFLICTING_INSTRUMENT_PRICES'
      : _savedPriceAt(asOf, lastKnown) != null
      ? 'RECOVERED_LAST_KNOWN'
      : 'UNAVAILABLE';
}

class ShadowMarketSnapshot {
  final String status;
  final List<ShadowQuote> rows;
  ShadowMarketSnapshot._(this.status, this.rows);
  factory ShadowMarketSnapshot.fromJson(Object? payload) {
    if (payload is! Map<String, dynamic> ||
        !{
          'app-market-preview/v1',
          'app-market-preview/v2',
          'app-market-preview/v3',
        }.contains(payload['contract']) ||
        payload['mode'] != 'SHADOW_ONLY' ||
        !{
          'AVAILABLE',
          'DISABLED',
          'WAITING',
          'SOURCE_DISABLED',
          'EVIDENCE_UNAVAILABLE',
        }.contains(payload['status']) ||
        payload['rows'] is! List ||
        (payload['rows'] as List).length > 2048 ||
        _previewTime(payload['as_of']) == null) {
      throw const BackendFailure('Invalid market preview feed.');
    }
    final rows = (payload['rows'] as List).map((row) {
      if (row is! Map<String, dynamic>) {
        throw const BackendFailure('Invalid market preview row.');
      }
      return ShadowQuote.fromJson(
        row,
        withReferences: payload['contract'] != 'app-market-preview/v1',
        withApplication: payload['contract'] == 'app-market-preview/v3',
        feedCapture: _previewTime(payload['captured_at']),
      );
    }).toList();
    if ((payload['status'] != 'AVAILABLE' && rows.isNotEmpty) ||
        rows.map((row) => row.assetKey).toSet().length != rows.length) {
      throw const BackendFailure('Invalid market preview universe.');
    }
    return ShadowMarketSnapshot._(payload['status'], List.unmodifiable(rows));
  }
}

class ShadowMarketFeedClient {
  final Future<Object?> Function() _read;
  ShadowMarketFeedClient(SupabaseClient client, {bool applicationRows = false})
    : _read = (() async {
        if (client.auth.currentSession == null) {
          throw const BackendFailure('Please sign in to view market data.');
        }
        return await client.rpc(
          applicationRows
              ? 'read_shadow_application_feed'
              : 'read_shadow_market_feed',
        );
      });
  ShadowMarketFeedClient.withReader(this._read);

  Future<ShadowMarketSnapshot> read() async {
    try {
      return ShadowMarketSnapshot.fromJson(await _read());
    } on BackendFailure {
      rethrow;
    } catch (_) {
      throw const BackendFailure('Market preview is temporarily unavailable.');
    }
  }
}
