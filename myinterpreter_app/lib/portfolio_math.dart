/// Shared display-estimate contract mirrored in core/portfolio_math.php.
/// Stored trade amounts and holding snapshots are never rewritten here.
library;

int _time(String value) {
  final match = RegExp(r'^(\d{4})-(\d{2})-(\d{2})(?:T| )').firstMatch(value);
  if (match == null || !RegExp(r'(?:Z|[+-]\d{2}:\d{2})$').hasMatch(value)) {
    throw const FormatException(
      'Trade timestamp requires a date and timezone.',
    );
  }
  final year = int.parse(match[1]!);
  final month = int.parse(match[2]!);
  final day = int.parse(match[3]!);
  final calendar = DateTime.utc(year, month, day);
  if (calendar.year != year || calendar.month != month || calendar.day != day) {
    throw const FormatException('Invalid trade date.');
  }
  return DateTime.parse(value).microsecondsSinceEpoch;
}

double _positive(Object? value) {
  final parsed = value is num
      ? value.toDouble()
      : value is String
      ? double.tryParse(value)
      : null;
  if (parsed == null || !parsed.isFinite || parsed <= 0) {
    throw const FormatException('Invalid trade amount.');
  }
  return parsed;
}

class _Lot {
  final Map<String, dynamic> source;
  final int time;
  final String id;
  final double price;
  double left;
  _Lot(this.source, this.time, this.id, this.left, this.price);
  _Lot copy() => _Lot(source, time, id, left, price);
}

/// One company's buys/sells using the normalized DATE/NUMBER/PRIX_* fields.
List<Map<String, dynamic>> fifoMatches(
  List<Map<String, dynamic>> buys,
  List<Map<String, dynamic>> sells,
) {
  const epsilon = 1e-9;
  final lots =
      <_Lot>[
        for (var i = 0; i < buys.length; i++)
          _Lot(
            buys[i],
            _time(buys[i]['DATE'] as String),
            '${buys[i]['ID'] ?? i}',
            _positive(buys[i]['NUMBER']),
            _positive(buys[i]['PRIX_ACHAT']),
          ),
      ]..sort((a, b) {
        final order = a.time.compareTo(b.time);
        return order != 0 ? order : a.id.compareTo(b.id);
      });
  final sales =
      <_Lot>[
        for (var i = 0; i < sells.length; i++)
          _Lot(
            sells[i],
            _time(sells[i]['DATE'] as String),
            '${sells[i]['ID'] ?? i}',
            _positive(sells[i]['NUMBER']),
            _positive(sells[i]['PRIX_VENTE']),
          ),
      ]..sort((a, b) {
        final order = a.time.compareTo(b.time);
        return order != 0 ? order : a.id.compareTo(b.id);
      });
  final rows = <Map<String, dynamic>>[];
  for (var saleIndex = 0; saleIndex < sales.length; saleIndex++) {
    final sale = sales[saleIndex];
    final work = lots.map((l) => l.copy()).toList();
    final pending = <Map<String, dynamic>>[];
    var left = sale.left;
    String? error;
    for (var i = 0; i < work.length && left > epsilon;) {
      if (work[i].left <= epsilon) {
        i++;
        continue;
      }
      if (work[i].time > sale.time) break;
      if (work[i].time == sale.time) {
        error = 'AMBIGUOUS_TRADE_ORDER';
        break;
      }
      final group = <int>[];
      var total = 0.0;
      final prices = <double>{};
      final stamp = work[i].time;
      var j = i;
      while (j < work.length && work[j].time == stamp) {
        if (work[j].left > epsilon) {
          group.add(j);
          total += work[j].left;
          prices.add(work[j].price);
        }
        j++;
      }
      if (left + epsilon < total && prices.length > 1) {
        error = 'AMBIGUOUS_LOT_ORDER';
        break;
      }
      for (final index in group) {
        if (left <= epsilon) break;
        final lot = work[index];
        final quantity = left < lot.left ? left : lot.left;
        final buyAmount = quantity * lot.price;
        final sellAmount = quantity * sale.price;
        pending.add({
          'sale_id': sale.id,
          'achat_date': lot.source['DATE'],
          'achat_nombre': quantity,
          'achat_prix': lot.price,
          'achat_montant': buyAmount,
          'vente_date': sale.source['DATE'],
          'vente_nombre': quantity,
          'vente_prix': sale.price,
          'vente_montant': sellAmount,
          'duree_days': (sale.time - lot.time) ~/ Duration.microsecondsPerDay,
          'benefice': sellAmount - buyAmount,
          'is_split': quantity + epsilon < _positive(lot.source['NUMBER']),
        });
        work[index].left -= quantity;
        left -= quantity;
      }
      i = j;
    }
    if (error != null || left > epsilon) {
      rows.add({
        'sale_id': sale.id,
        'error': error ?? 'INCOMPLETE_BUY_HISTORY',
        'vente_date': sale.source['DATE'],
      });
      for (var next = saleIndex + 1; next < sales.length; next++) {
        rows.add({
          'sale_id': sales[next].id,
          'error': 'PRIOR_SALE_UNRESOLVED',
          'vente_date': sales[next].source['DATE'],
        });
      }
      break;
    }
    lots
      ..clear()
      ..addAll(work);
    rows.addAll(pending);
  }
  return rows;
}

Map<String, dynamic> realizedTotals(
  List<Map<String, dynamic>> rows,
  double commissionRate,
  double taxRate,
) {
  var gross = 0.0;
  var fees = 0.0;
  var unresolved = 0;
  for (final row in rows) {
    if (row.containsKey('error')) {
      unresolved++;
      continue;
    }
    gross += (row['benefice'] as num).toDouble();
    fees +=
        ((row['achat_montant'] as num) + (row['vente_montant'] as num)) *
        commissionRate;
  }
  final tax = (gross > 0 ? gross : 0.0) * taxRate;
  return {
    'gross': gross,
    'fees': fees,
    'tax': tax,
    'net': gross - fees - tax,
    'unresolved_sales': unresolved,
  };
}
