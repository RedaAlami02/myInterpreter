import 'recorded_market_list.dart';
import 'dart:async';
import 'package:flutter/material.dart';
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

class _MarketPreviewListState extends State<MarketPreviewList> {
  late Future<ShadowMarketSnapshot?> _future;
  String _search = '';
  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  @override
  void didUpdateWidget(covariant MarketPreviewList oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(widget.source, oldWidget.source)) {
      _search = '';
      _future = _load();
    }
  }

  Future<ShadowMarketSnapshot?> _load() async {
    if (!widget.source.marketDisplayEnabled) {
      return null;
    }
    try {
      return ShadowMarketSnapshot.fromJson(
        await widget.source.readMarketDisplay(),
      );
    } catch (_) {
      return null; // No raw network/parser diagnostics enter the screen or logs.
    }
  }

  Future<void> _refresh() async {
    final result = _load();
    setState(() {
      _future = result;
    });
    await result;
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<ShadowMarketSnapshot?>(
    future: _future,
    builder: (context, state) {
      if (state.connectionState != ConnectionState.done) {
        return const Center(child: CircularProgressIndicator());
      }
      if (state.hasError ||
          state.data?.status != 'AVAILABLE' ||
          state.data!.rows.isEmpty) {
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
      final snapshot = state.data!;
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
          final visible = rows.asMap().entries.where(
            (entry) => '${entry.value['c_name']} ${entry.value['symbol']}'
                .toLowerCase()
                .contains(_search),
          );
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
    },
  );
}
