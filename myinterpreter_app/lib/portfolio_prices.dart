import 'package:timezone/data/latest.dart' as tzdata;
import 'package:timezone/timezone.dart' as tz;

/// Informational recorded-price estimates, never authority for saved valuations.
class RecordedPortfolioPrice {
  final double? price;
  final String? day;
  final String status;
  const RecordedPortfolioPrice(this.price, this.day, this.status);
}

Map<String, RecordedPortfolioPrice> recordedPortfolioPrices(
  List<Map<String, dynamic>> records, {
  DateTime? now,
}) {
  final result = <String, RecordedPortfolioPrice>{};
  final moment = now ?? DateTime.now().toUtc();
  for (final row in records) {
    final name = row['c_name'];
    if (name is! String || name.isEmpty) continue;
    if (result.containsKey(name)) {
      result[name] = const RecordedPortfolioPrice(null, null, 'CONFLICT');
      continue;
    }
    final raw = row['pa'];
    final price = raw is num
        ? raw.toDouble()
        : raw is String && RegExp(r'^\d+(?:\.\d+)?$').hasMatch(raw)
        ? double.tryParse(raw)
        : null;
    result[name] = const RecordedPortfolioPrice(null, null, 'UNAVAILABLE');
    if (price == null || !price.isFinite || price <= 0 || price > 1e12) {
      continue;
    }
    final date = row['date'];
    final parts = date is String
        ? RegExp(
            r'^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|([+-])(\d{2}):(\d{2}))$',
          ).firstMatch(date)
        : null;
    DateTime? stamp;
    if (parts != null) {
      final year = int.parse(parts[1]!);
      final month = int.parse(parts[2]!);
      final day = int.parse(parts[3]!);
      final calendar = DateTime.utc(year, month, day);
      if (year >= 1 &&
          calendar.year == year &&
          calendar.month == month &&
          calendar.day == day &&
          int.parse(parts[4]!) < 24 &&
          int.parse(parts[5]!) < 60 &&
          int.parse(parts[6]!) < 60 &&
          (parts[9] == null ||
              (int.parse(parts[9]!) < 24 && int.parse(parts[10]!) < 60))) {
        stamp = DateTime.tryParse(date as String)?.toUtc();
      }
    }
    if (stamp == null) {
      result[name] = const RecordedPortfolioPrice(null, null, 'UNKNOWN_DATE');
    } else if (stamp.isAfter(moment)) {
      result[name] = const RecordedPortfolioPrice(null, null, 'FUTURE_DATE');
    } else {
      result[name] = RecordedPortfolioPrice(
        price,
        stamp.toIso8601String().substring(0, 10),
        'RECORDED_REFERENCE',
      );
    }
  }
  return result;
}

class PortfolioReferenceTotals {
  final double? invested, value, pnl;
  final String? day;
  final int covered, positions;
  bool get complete => value != null;
  bool get portfolioValuationEligible => false;
  const PortfolioReferenceTotals(
    this.invested,
    this.value,
    this.pnl,
    this.day,
    this.covered,
    this.positions,
  );
}

PortfolioReferenceTotals portfolioReferenceTotals(
  List<Map<String, dynamic>> holdings,
  Map<String, RecordedPortfolioPrice> prices, {
  bool holdingsComplete = true,
}) {
  double invested = 0, value = 0;
  var covered = 0, valid = true;
  final days = <String?>{};
  for (final holding in holdings) {
    final qty = holding['quantity'], cost = holding['total_cost'];
    if (qty is! num ||
        cost is! num ||
        !qty.isFinite ||
        !cost.isFinite ||
        qty <= 0 ||
        cost < 0) {
      valid = false;
      continue;
    }
    invested += cost;
    final quote = prices[holding['c_name']];
    if (quote?.price == null) continue;
    value += qty * quote!.price!;
    covered++;
    days.add(quote.day);
  }
  final complete =
      holdingsComplete &&
      valid &&
      holdings.isNotEmpty &&
      covered == holdings.length &&
      days.length == 1 &&
      value.isFinite &&
      invested.isFinite;
  return PortfolioReferenceTotals(
    valid && holdingsComplete ? invested : null,
    complete ? value : null,
    complete ? value - invested : null,
    complete ? days.single : null,
    covered,
    holdings.length,
  );
}

final tz.Location _marketLocation = (() {
  tzdata.initializeTimeZones();
  return tz.getLocation('Africa/Casablanca');
})();

/// Display copies only: originals and official-close valuations are untouched.
Map<String, RecordedPortfolioPrice> portfolioDisplayPrices(
  List<Map<String, dynamic>> recorded,
  List<Map<String, dynamic>> displayRows, {
  DateTime? now,
}) {
  final moment = now ?? DateTime.now().toUtc();
  final local = tz.TZDateTime.from(moment, _marketLocation);
  final day =
      '${local.year.toString().padLeft(4, '0')}-${local.month.toString().padLeft(2, '0')}-${local.day.toString().padLeft(2, '0')}';
  final result = recordedPortfolioPrices(recorded, now: moment);
  final seen = <String>{};
  for (final row in displayRows) {
    final metadata = row['_market_display'];
    if (metadata is! Map ||
        metadata['available'] != true ||
        metadata['price_basis'] != 'REPORTED_QUOTE' ||
        metadata['reported_day'] != day ||
        metadata['asset_key'] is! String ||
        !(metadata['asset_key'] as String).startsWith('company:')) {
      continue;
    }
    final captured = DateTime.tryParse(
      metadata['captured_at'] as String? ?? '',
    );
    final expiry = DateTime.tryParse(metadata['expires_at'] as String? ?? '');
    final name = row['c_name'];
    final raw = metadata['price_decimal'];
    final price = raw is String ? double.tryParse(raw) : null;
    if (name is! String ||
        name.isEmpty ||
        captured == null ||
        expiry == null ||
        captured.isAfter(moment) ||
        !moment.isBefore(expiry) ||
        price == null ||
        !price.isFinite ||
        price <= 0 ||
        price > 1e12) {
      continue;
    }
    if (!seen.add(name)) {
      result[name] = const RecordedPortfolioPrice(null, null, 'CONFLICT');
    } else {
      result[name] = RecordedPortfolioPrice(
        price,
        day,
        'CURRENT_REPORTED_QUOTE',
      );
    }
  }
  return result;
}
