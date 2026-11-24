import 'loading_rows.dart';
import 'recorded_market_list.dart';
import 'dart:async';
import 'package:flutter/material.dart';
import 'app_colors.dart' show kAccent, kBorder, kTextMuted;
import 'backend_contract.dart';
import 'shadow_market_feed.dart';

bool marketPreviewEnabled(AppBackend app) =>
    app is MarketDisplayBackend &&
    (app as MarketDisplayBackend).marketDisplayEnabled;

/// Display maps only. They never enter AppDocument or the portfolio backend.
List<Map<String, dynamic>> marketPreviewRowsAt(
  List<ShadowQuote> quotes,
  DateTime now,
) => quotes
    .map((quote) {
      final view = quote.applicationRowAt(now);
      final fields = view == null
          ? const <String, dynamic>{}
          : view['fields'] as Map<String, dynamic>;
      return <String, dynamic>{
        ...fields,
        'c_name': quote.name,
        'symbol': quote.symbol,
        '_market_display': <String, dynamic>{
          ...?view,
          'instrument_type': quote.instrumentType,
          'expired':
              quote.applicationExpiresAt != null &&
              !now.isBefore(quote.applicationExpiresAt!),
          'available': view != null,
        },
      };
    })
    .toList(growable: false);

String marketUtcTime(String value) {
  final time = DateTime.parse(value).toUtc();
  String two(int part) => part.toString().padLeft(2, '0');
  return '${two(time.day)}/${two(time.month)}/${time.year} ${two(time.hour)}:${two(time.minute)} UTC';
}

class MarketPriceContext extends StatelessWidget {
  final Map<String, dynamic> row;
  const MarketPriceContext({super.key, required this.row});
  @override
  Widget build(BuildContext context) {
    final metadata = row['_market_display'] as Map<String, dynamic>;
    final available = metadata['available'] == true;
    final reference = metadata['price_basis'] == 'INSTRUMENT_REFERENCE';
    final day = metadata['reported_day'] as String?;
    final event = metadata['source_event_at'] as String?;
    final label = !available
        ? (metadata['expired'] == true
              ? 'Prix expiré — actualisez'
              : 'Prix indisponible')
        : reference
        ? 'Prix de référence'
        : 'Cours annoncé';
    return Text(
      [
        label,
        if (available)
          reference
              ? 'Date de cotation inconnue.'
              : event != null
              ? 'Coté le ${marketUtcTime(event)}'
              : day != null
              ? 'Date annoncée : ${day.split('-').reversed.join('/')} — heure inconnue'
              : 'Date de cotation inconnue.',
        if (available)
          'Reçu le ${marketUtcTime(metadata['captured_at'] as String)}',
      ].join('\n'),
      style: Theme.of(context).textTheme.bodySmall,
    );
  }
}

/// Recheck on expiry and resume; no periodic network request or cached valuation.
class ExpiringMarketRows extends StatefulWidget {
  final List<ShadowQuote> quotes;
  final Widget Function(BuildContext, List<Map<String, dynamic>>) builder;
  final DateTime Function()? clock;
  const ExpiringMarketRows({
    super.key,
    required this.quotes,
    required this.builder,
    this.clock,
  });
  @override
  State<ExpiringMarketRows> createState() => _ExpiringMarketRowsState();
}

class _ExpiringMarketRowsState extends State<ExpiringMarketRows>
    with WidgetsBindingObserver {
  Timer? _timer;
  DateTime get _now => widget.clock?.call() ?? DateTime.now();
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _schedule();
  }

  @override
  void didUpdateWidget(covariant ExpiringMarketRows oldWidget) {
    super.didUpdateWidget(oldWidget);
    _schedule();
  }

  void _schedule() {
    _timer?.cancel();
    final now = _now;
    final upcoming =
        widget.quotes
            .map((quote) => quote.applicationExpiresAt)
            .whereType<DateTime>()
            .where((expiry) => expiry.isAfter(now))
            .toList()
          ..sort();
    if (upcoming.isNotEmpty) {
      _timer = Timer(upcoming.first.difference(now), () {
        if (!mounted) return;
        setState(() {});
        _schedule();
      });
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted) {
      setState(() {});
      _schedule();
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      widget.builder(context, marketPreviewRowsAt(widget.quotes, _now));
}

enum _MarketSort { name, change, per, price }

class MarketPreviewList extends StatefulWidget {
  final MarketDisplayBackend source;
  final Widget Function(Map<String, dynamic>, ShadowQuote) cardBuilder;
  final DateTime Function()? clock;
  const MarketPreviewList({
    super.key,
    required this.source,
    required this.cardBuilder,
    this.clock,
  });
  @override
  State<MarketPreviewList> createState() => _MarketPreviewListState();
}

class _MarketPreviewListState extends State<MarketPreviewList>
    with WidgetsBindingObserver {
  /// One fetch and then silence let every quote expire while the screen was
  /// open; the website polls, so this does too, and pauses with the app.
  static const _interval = Duration(seconds: 60);

  ShadowMarketSnapshot? _snapshot;
  bool _unusable = false;
  bool _settled = false;
  bool _inFlight = false;
  int _failures = 0;
  Timer? _poll;
  String _search = '';
  _MarketSort _sort = _MarketSort.name;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _load();
    _arm(_interval);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _poll?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed) return;
    _load();
    _arm(_interval);
  }

  @override
  void didUpdateWidget(covariant MarketPreviewList oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(widget.source, oldWidget.source)) {
      _search = '';
      _snapshot = null;
      _unusable = false;
      _settled = false;
      _load();
    }
  }

  void _arm(Duration delay) {
    _poll?.cancel();
    _poll = Timer(delay, () {
      _load();
      _arm(_delay());
    });
  }

  Duration _delay() {
    if (_failures == 0) return _interval;
    final seconds = 60 << (_failures > 4 ? 4 : _failures);
    return Duration(seconds: seconds > 600 ? 600 : seconds);
  }

  Future<void> _load() async {
    if (_inFlight) return;
    if (!widget.source.marketDisplayEnabled) {
      if (mounted) setState(() => _settled = true);
      return;
    }
    _inFlight = true;
    try {
      final snapshot = ShadowMarketSnapshot.fromJson(
        await widget.source.readMarketDisplay(),
      );
      final usable = snapshot.status == 'AVAILABLE' && snapshot.rows.isNotEmpty;
      if (!mounted) return;
      setState(() {
        _snapshot = snapshot;
        _unusable = !usable;
        _failures = usable ? 0 : _failures + 1;
        _settled = true;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _unusable = true;
        _failures++;
        _settled = true;
      });
    } finally {
      _inFlight = false;
    }
  }

  Future<void> _refresh() async {
    await _load();
    _arm(_interval);
  }

  @override
  Widget build(BuildContext context) {
    if (!_settled) return const LoadingRows();
    final snapshot = _snapshot;
    if (snapshot == null ||
        _unusable ||
        snapshot.status != 'AVAILABLE' ||
        snapshot.rows.isEmpty) {
      if (widget.source is AppBackend) {
        return RecordedMarketList(
          source: widget.source as AppBackend,
          onRefresh: _refresh,
        );
      }
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text(
                'Les cours récents sont indisponibles. Réessayez plus tard.',
                textAlign: TextAlign.center,
              ),
              TextButton(
                onPressed: () {
                  _refresh().catchError((Object _) {});
                },
                child: const Text('Actualiser'),
              ),
            ],
          ),
        ),
      );
    }
    return ExpiringMarketRows(
      quotes: snapshot.rows,
      clock: widget.clock,
      builder: (context, rows) {
        if (widget.source is AppBackend &&
            !rows.any(
              (row) =>
                  (row['_market_display']
                      as Map<String, dynamic>)['available'] ==
                  true,
            )) {
          return RecordedMarketList(
            source: widget.source as AppBackend,
            onRefresh: _refresh,
          );
        }
        final visible = <MapEntry<int, Map<String, dynamic>>>[];
        for (final entry in rows.asMap().entries) {
          if ('${entry.value['c_name']} ${entry.value['symbol']}'
              .toLowerCase()
              .contains(_search)) {
            visible.add(entry);
          }
        }
        visible.sort(_compare);
        return Column(
          children: [
            const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'Aperçu du marché\nLes prix de référence ne confirment pas une transaction récente.',
              ),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12),
              child: TextField(
                decoration: const InputDecoration(
                  labelText: 'Société ou symbole',
                  prefixIcon: Icon(Icons.search),
                ),
                onChanged: (value) =>
                    setState(() => _search = value.toLowerCase().trim()),
              ),
            ),
            _sortRow(),
            Expanded(
              child: RefreshIndicator(
                onRefresh: () async {
                  try {
                    await _refresh();
                  } catch (_) {}
                },
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  children: [
                    if (visible.isEmpty)
                      const Padding(
                        padding: EdgeInsets.all(24),
                        child: Text(
                          'Aucune société ne correspond à votre recherche.',
                        ),
                      ),
                    ...visible.map(
                      (entry) => widget.cardBuilder(
                        entry.value,
                        snapshot.rows[entry.key],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _sortRow() => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
    child: Row(
      children: [
        for (final sort in _MarketSort.values)
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: _sortChip(sort),
          ),
      ],
    ),
  );

  Widget _sortChip(_MarketSort sort) {
    final active = _sort == sort;
    return GestureDetector(
      onTap: () => setState(() => _sort = sort),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: active ? kAccent.withValues(alpha: 0.15) : Colors.transparent,
          borderRadius: BorderRadius.circular(9),
          border: Border.all(
            color: active ? kAccent.withValues(alpha: 0.5) : kBorder,
          ),
        ),
        child: Text(
          _sortLabel(sort),
          style: TextStyle(
            color: active ? kAccent : kTextMuted,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }

  static String _sortLabel(_MarketSort sort) => switch (sort) {
    _MarketSort.name => 'Société',
    _MarketSort.change => 'Δ% ↓',
    _MarketSort.per => 'PER ↑',
    _MarketSort.price => 'Cours ↓',
  };

  int _compare(
    MapEntry<int, Map<String, dynamic>> a,
    MapEntry<int, Map<String, dynamic>> b,
  ) {
    final left = a.value, right = b.value;
    final rank = _rank(left).compareTo(_rank(right));
    if (rank != 0) return rank;
    final name = '${left['c_name']}'.compareTo('${right['c_name']}');
    if (_sort == _MarketSort.name) return name;
    final key = switch (_sort) {
      _MarketSort.change => 'variation',
      _MarketSort.per => 'per',
      _MarketSort.price => 'pa',
      _MarketSort.name => 'c_name',
    };
    final x = _number(left[key]), y = _number(right[key]);
    if (x == null && y == null) return name;
    if (x == null) return 1;
    if (y == null) return -1;
    final order = _sort == _MarketSort.per ? x.compareTo(y) : y.compareTo(x);
    return order != 0 ? order : name;
  }

  static num? _number(Object? value) => value is num ? value : null;

  static int _rank(Map<String, dynamic> row) =>
      (row['_market_display'] as Map?)?['instrument_type'] == 'INDEX' ? 0 : 1;
}
