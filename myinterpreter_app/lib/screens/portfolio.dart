import 'package:flutter/material.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import 'buy_sell_sheet.dart';

class PortfolioScreen extends StatefulWidget {
  const PortfolioScreen({super.key});
  @override
  State<PortfolioScreen> createState() => _PortfolioScreenState();
}

class _PortfolioScreenState extends State<PortfolioScreen> {
  late Future<List<Map<String, dynamic>>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final me = await account.get();
    final res = await tablesDB.listRows(
      databaseId: dbId,
      tableId: 'portefeuille',
      queries: [Query.equal('user_id', me.$id), Query.limit(200)],
    );
    return res.rows.map((d) => d.data).toList();
  }

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
                onPressed: () => setState(() => _future = _load()),
                child: const Text('Retry'),
              ),
            ],
          ),
        );
      }
      if (!snap.hasData) return const Center(child: CircularProgressIndicator());
      final rows = snap.data!;
      if (rows.isEmpty) return const Center(child: Text('No holdings'));
      return RefreshIndicator(
        onRefresh: () {
          setState(() => _future = _load());
          return _future;
        },
        child: ListView.builder(
          itemCount: rows.length,
          itemBuilder: (_, i) {
            final r = rows[i];
            final qty = r['quantity'] ?? 0;
            final cost = r['total_cost'] ?? 0;
            final avg = qty > 0 ? (cost / qty) : 0;
            return ListTile(
              title: Text(r['c_name'] ?? '?'),
              subtitle: Text('Qty: $qty  Avg cost: ${avg.toStringAsFixed(2)}'),
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(cost.toStringAsFixed(2)),
                  IconButton(
                    icon: const Icon(Icons.sell),
                    onPressed: () async {
                      final name = r['c_name'] as String? ?? '';
                      final qty = (r['quantity'] as num?)?.toDouble() ?? 0;
                      final cost = (r['total_cost'] as num?)?.toDouble() ?? 0;
                      final avg = qty > 0 ? cost / qty : 0.0;
                      if (name.isEmpty) return;
                      await showBuySellSheet(context, name, avg, isBuy: false);
                      if (mounted) setState(() => _future = _load());
                    },
                  ),
                ],
              ),
            );
          },
        ),
      );
    },
  );
}
