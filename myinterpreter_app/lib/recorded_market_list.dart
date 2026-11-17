import 'package:flutter/material.dart';
import 'backend_contract.dart';
import 'portfolio_prices.dart';
import 'query.dart';

/// Read-only dated fallback; it never supplies execution or saved valuation prices.
class RecordedMarketList extends StatefulWidget {
  final AppBackend source;
  final Future<void> Function() onRefresh;
  const RecordedMarketList({
    super.key,
    required this.source,
    required this.onRefresh,
  });
  @override
  State<RecordedMarketList> createState() => _RecordedMarketListState();
}

class _RecordedMarketListState extends State<RecordedMarketList> {
  late Future<Map<String, RecordedPortfolioPrice>> _prices;
  String _search = '';
  Future<Map<String, RecordedPortfolioPrice>> _load() async {
    final page = await widget.source.listDocuments(
      collectionId: 'latest_prices',
      queries: [Query.limit(500)],
    );
    return recordedPortfolioPrices(page.documents.map((d) => d.data).toList());
  }

  @override
  void initState() {
    super.initState();
    _prices = _load();
  }

  @override
  void didUpdateWidget(covariant RecordedMarketList oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.source, widget.source)) _prices = _load();
  }

  Future<void> _refresh() async {
    setState(() {
      _prices = _load();
    });
    await widget.onRefresh();
  }

  @override
  Widget build(
    BuildContext context,
  ) => FutureBuilder<Map<String, RecordedPortfolioPrice>>(
    future: _prices,
    builder: (context, snapshot) {
      final entries =
          (snapshot.data?.entries ??
                  const <MapEntry<String, RecordedPortfolioPrice>>[])
              .where(
                (e) =>
                    e.value.price != null &&
                    e.value.day != null &&
                    e.key.toLowerCase().contains(_search),
              )
              .toList()
            ..sort((a, b) => a.key.compareTo(b.key));
      return Column(
        children: [
          const Padding(
            padding: EdgeInsets.all(12),
            child: Text(
              'Cours récents indisponibles. Prix enregistrés ci-dessous ; ils ne sont pas des cotations en direct.',
            ),
          ),
          TextButton(onPressed: _refresh, child: const Text('Actualiser')),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: TextField(
              decoration: const InputDecoration(
                labelText: 'Société',
                prefixIcon: Icon(Icons.search),
              ),
              onChanged: (value) => setState(() {
                _search = value.toLowerCase().trim();
              }),
            ),
          ),
          Expanded(
            child: snapshot.connectionState != ConnectionState.done
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _refresh,
                    child: ListView.builder(
                      physics: const AlwaysScrollableScrollPhysics(),
                      itemCount: entries.isEmpty ? 1 : entries.length,
                      itemBuilder: (context, index) {
                        if (entries.isEmpty) {
                          return Padding(
                            padding: const EdgeInsets.all(24),
                            child: Text(
                              snapshot.hasError
                                  ? 'Prix enregistrés indisponibles. Réessayez.'
                                  : 'Aucun prix enregistré ne correspond à votre recherche.',
                            ),
                          );
                        }
                        final item = entries[index];
                        return ListTile(
                          title: Text(item.key),
                          subtitle: Text(
                            'Prix enregistré · ${item.value.day} (UTC)',
                          ),
                          trailing: Text(
                            '${item.value.price!.toStringAsFixed(2)} MAD',
                          ),
                        );
                      },
                    ),
                  ),
          ),
        ],
      );
    },
  );
}
