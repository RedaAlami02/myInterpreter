import 'package:flutter/material.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';

class StatisticsScreen extends StatefulWidget {
  const StatisticsScreen({super.key});
  @override
  State<StatisticsScreen> createState() => _StatisticsScreenState();
}

class _StatisticsScreenState extends State<StatisticsScreen> {
  late Future<Map<String, dynamic>> _future;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<Map<String, dynamic>> _load() async {
    final me = await account.get();
    final userId = me.$id;

    final dataRes = await tablesDB.listRows(
      databaseId: dbId,
      tableId: 'data',
      queries: [Query.orderDesc('date'), Query.limit(500)],
    );
    final latest = <String, Map<String, dynamic>>{};
    for (final d in dataRes.rows) {
      final n = d.data['c_name'] as String?;
      if (n != null && !latest.containsKey(n)) latest[n] = d.data;
    }
    final counts = {'green': 0, 'orange': 0, 'red': 0, 'total': latest.length};
    for (final r in latest.values) {
      final k = r['per_rating'] as String?;
      if (k != null && counts.containsKey(k)) counts[k] = counts[k]! + 1;
    }

    final ventesRes = await tablesDB.listRows(
      databaseId: dbId,
      tableId: 'ventes',
      queries: [Query.equal('user_id', userId), Query.limit(500)],
    );
    final achatsRes = await tablesDB.listRows(
      databaseId: dbId,
      tableId: 'achats',
      queries: [Query.equal('user_id', userId), Query.limit(500)],
    );

    final buyMap = <String, List<Map<String, dynamic>>>{};
    for (final d in achatsRes.rows) {
      final name = d.data['c_name'] as String? ?? '';
      buyMap.putIfAbsent(name, () => []).add(d.data);
    }

    final gains = <Map<String, dynamic>>[];
    for (final d in ventesRes.rows) {
      final name = d.data['c_name'] as String? ?? '';
      final sellPrice = (d.data['price'] as num?)?.toDouble() ?? 0;
      final sellQty = (d.data['quantity'] as num?)?.toDouble() ?? 0;
      final buys = buyMap[name] ?? [];
      double totalCost = 0, totalQty = 0;
      for (final b in buys) {
        totalCost += ((b['price'] as num?)?.toDouble() ?? 0) * ((b['quantity'] as num?)?.toDouble() ?? 0);
        totalQty += (b['quantity'] as num?)?.toDouble() ?? 0;
      }
      final avgCost = totalQty > 0 ? totalCost / totalQty : 0.0;
      final gain = (sellPrice - avgCost) * sellQty;
      gains.add({'c_name': name, 'gain': gain, 'qty': sellQty, 'date': d.data['date']});
    }

    final totalGain = gains.fold<double>(0, (s, g) => s + (g['gain'] as double));
    const taxRate = 0.15;
    final taxOwed = totalGain > 0 ? totalGain * taxRate : 0.0;

    return {'counts': counts, 'gains': gains, 'totalGain': totalGain, 'taxOwed': taxOwed};
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      onRefresh: () {
        final f = _load();
        setState(() => _future = f);
        return f;
      },
      child: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (ctx, snap) {
          if (snap.hasError) {
            return ListView(
              children: [
                SizedBox(
                  height: MediaQuery.of(ctx).size.height * 0.8,
                  child: Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.error_outline, size: 48, color: Colors.red),
                        const SizedBox(height: 16),
                        Text('Error: ${snap.error}', textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: () => setState(() => _future = _load()),
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            );
          }
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final counts = snap.data!['counts'] as Map<String, dynamic>;
          final gains = snap.data!['gains'] as List<Map<String, dynamic>>;
          final totalGain = snap.data!['totalGain'] as double;
          final taxOwed = snap.data!['taxOwed'] as double;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Center(
                child: Text(
                  'Total stocks: ${counts['total']}',
                  style: const TextStyle(fontSize: 20),
                ),
              ),
              const SizedBox(height: 16),
              Center(
                child: Text(
                  'PER green:  ${counts['green']}',
                  style: const TextStyle(color: Colors.green),
                ),
              ),
              Center(
                child: Text(
                  'PER orange: ${counts['orange']}',
                  style: const TextStyle(color: Colors.orange),
                ),
              ),
              Center(
                child: Text(
                  'PER red:    ${counts['red']}',
                  style: const TextStyle(color: Colors.red),
                ),
              ),
              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              const Text(
                'Realized Gains',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 8),
              ...gains.map((g) {
                final gain = g['gain'] as double;
                return ListTile(
                  title: Text(g['c_name'] as String),
                  subtitle: Text(g['date']?.toString() ?? ''),
                  trailing: Text(
                    gain.toStringAsFixed(2),
                    style: TextStyle(
                      color: gain >= 0 ? Colors.green : Colors.red,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                );
              }),
              const Divider(),
              const SizedBox(height: 8),
              Center(
                child: Text(
                  'Total gain: ${totalGain.toStringAsFixed(2)}  |  Tax (15%): ${taxOwed.toStringAsFixed(2)}',
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                ),
              ),
              const SizedBox(height: 16),
            ],
          );
        },
      ),
    );
  }
}
