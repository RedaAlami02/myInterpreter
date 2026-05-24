import 'package:flutter/material.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import 'stock_detail.dart';
import 'buy_sell_sheet.dart';

class ScreenerScreen extends StatefulWidget {
  const ScreenerScreen({super.key});
  @override
  State<ScreenerScreen> createState() => _ScreenerScreenState();
}

class _ScreenerScreenState extends State<ScreenerScreen> {
  late Future<List<Map<String, dynamic>>> _future;
  final TextEditingController _search = TextEditingController();

  @override
  void initState() {
    super.initState();
    _future = _loadLatest();
    _search.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  Future<List<Map<String, dynamic>>> _loadLatest() async {
    final res = await tablesDB.listRows(
      databaseId: dbId,
      tableId: 'data',
      queries: [Query.orderDesc('date'), Query.limit(500)],
    );
    final latest = <String, Map<String, dynamic>>{};
    for (final d in res.rows) {
      final name = d.data['c_name'] as String?;
      if (name != null && !latest.containsKey(name)) latest[name] = d.data;
    }
    return latest.values.toList();
  }

  List<Map<String, dynamic>> _filter(List<Map<String, dynamic>> rows) {
    final q = _search.text.toLowerCase();
    if (q.isEmpty) return rows;
    return rows.where((r) => (r['c_name'] as String? ?? '').toLowerCase().contains(q)).toList();
  }

  Color _color(String? r) => switch (r) {
    'green' => Colors.green,
    'orange' => Colors.orange,
    'red' => Colors.red,
    _ => Colors.grey,
  };

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Map<String, dynamic>>>(
    future: _future,
    builder: (ctx, snap) {
      if (snap.hasError) {
        return Center(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.error_outline, size: 48, color: Colors.red),
              const SizedBox(height: 12),
              Text('${snap.error}'),
              const SizedBox(height: 12),
              ElevatedButton(
                onPressed: () => setState(() => _future = _loadLatest()),
                child: const Text('Retry'),
              ),
            ],
          ),
        );
      }
      if (!snap.hasData) return const Center(child: CircularProgressIndicator());
      final rows = _filter(snap.data!);
      return Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(8.0),
            child: TextField(
              controller: _search,
              decoration: const InputDecoration(
                hintText: 'Search stocks...',
                prefixIcon: Icon(Icons.search),
                border: OutlineInputBorder(),
                isDense: true,
              ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              onRefresh: () {
                final f = _loadLatest();
                setState(() => _future = f);
                return f;
              },
              child: ListView.builder(
                itemCount: rows.length,
                itemBuilder: (_, i) {
                  final r = rows[i];
                  return ListTile(
                    title: Text(r['c_name'] ?? '?'),
                    subtitle: Text('PA: ${r['pa']}  PER: ${r['per']?.toStringAsFixed(2) ?? '-'}'),
                    trailing: Wrap(
                      spacing: 4,
                      children: [
                        CircleAvatar(radius: 6, backgroundColor: _color(r['per_rating'])),
                        CircleAvatar(radius: 6, backgroundColor: _color(r['peg_rating'])),
                        CircleAvatar(radius: 6, backgroundColor: _color(r['pr_rating'])),
                        CircleAvatar(radius: 6, backgroundColor: _color(r['pb_rating'])),
                        IconButton(
                          icon: const Icon(Icons.add_shopping_cart),
                          onPressed: () async {
                            final name = r['c_name'] as String? ?? '';
                            final pa = (r['pa'] as num?)?.toDouble() ?? 0.0;
                            if (name.isEmpty) return;
                            await showBuySellSheet(context, name, pa, isBuy: true);
                            if (mounted) setState(() => _future = _loadLatest());
                          },
                        ),
                      ],
                    ),
                    onTap: () {
                      final name = r['c_name'] as String? ?? '';
                      if (name.isEmpty) return;
                      Navigator.push(context,
                        MaterialPageRoute(builder: (_) => StockDetailScreen(name: name)));
                    },
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
