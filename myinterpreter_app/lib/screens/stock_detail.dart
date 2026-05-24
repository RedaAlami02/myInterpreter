import 'package:flutter/material.dart';
import 'package:appwrite/appwrite.dart';
import 'package:fl_chart/fl_chart.dart';
import '../appwrite_client.dart';
import 'buy_sell_sheet.dart';

class StockDetailScreen extends StatefulWidget {
  final String name;
  const StockDetailScreen({super.key, required this.name});

  @override
  State<StockDetailScreen> createState() => _StockDetailScreenState();
}

class _StockDetailScreenState extends State<StockDetailScreen> {
  late Future<List<Map<String, dynamic>>> _future;
  String _range = 'Week';

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<List<Map<String, dynamic>>> _load() async {
    final now = DateTime.now();
    final cutoff = switch (_range) {
      'Today' => DateTime(now.year, now.month, now.day),
      'Week'  => now.subtract(const Duration(days: 7)),
      'Month' => DateTime(now.year, now.month - 1, now.day),
      _       => DateTime(now.year - 1, now.month, now.day),
    };
    final cutoffStr = cutoff.toUtc().toIso8601String();
    final res = await tablesDB.listRows(
      databaseId: dbId,
      tableId: 'data',
      queries: [
        Query.equal('c_name', widget.name),
        Query.greaterThanEqual('date', cutoffStr),
        Query.orderDesc('date'),
        Query.limit(2000),
      ],
    );
    return res.rows.map((d) => d.data).toList();
  }

  void _refresh() => setState(() => _future = _load());

  void _setRange(String range) => setState(() { _range = range; _future = _load(); });

  Widget _buildChart(List<Map<String, dynamic>> rows) {
    if (rows.isEmpty) {
      return const SizedBox(height: 220, child: Center(child: Text('No data for this range')));
    }
    final reversed = rows.reversed.toList();
    final spots = <FlSpot>[];
    for (int i = 0; i < reversed.length; i++) {
      final pa = (reversed[i]['pa'] as num?)?.toDouble();
      if (pa != null) spots.add(FlSpot(i.toDouble(), pa));
    }
    if (spots.isEmpty) return const SizedBox(height: 220);

    final minY = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
    final maxY = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    final padding = (maxY - minY) * 0.1 + 1;

    String labelAt(int idx) {
      final date = reversed[idx]['date'] as String? ?? '';
      return date.length >= 10 ? date.substring(0, 10) : date;
    }

    return Card(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(8, 16, 16, 8),
        child: SizedBox(
          height: 220,
          child: LineChart(
            LineChartData(
              minX: 0,
              maxX: (spots.length - 1).toDouble(),
              minY: minY - padding,
              maxY: maxY + padding,
              gridData: const FlGridData(show: true, drawVerticalLine: false),
              borderData: FlBorderData(show: false),
              titlesData: FlTitlesData(
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 48,
                    getTitlesWidget: (v, _) => Text(v.toStringAsFixed(0),
                      style: const TextStyle(fontSize: 10)),
                  ),
                ),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 28,
                    interval: spots.length <= 1 ? 1 : (spots.length - 1) / 2,
                    getTitlesWidget: (v, _) {
                      final idx = v.round();
                      if (idx < 0 || idx >= reversed.length) return const SizedBox();
                      return Padding(
                        padding: const EdgeInsets.only(top: 4),
                        child: Text(labelAt(idx), style: const TextStyle(fontSize: 9)),
                      );
                    },
                  ),
                ),
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              ),
              lineTouchData: LineTouchData(
                touchTooltipData: LineTouchTooltipData(
                  getTooltipItems: (spots) => spots.map((s) {
                    final idx = s.x.round();
                    final date = idx < reversed.length ? labelAt(idx) : '';
                    return LineTooltipItem('$date\n${s.y.toStringAsFixed(2)} MAD',
                      const TextStyle(fontSize: 12, color: Colors.white));
                  }).toList(),
                ),
              ),
              lineBarsData: [
                LineChartBarData(
                  spots: spots,
                  isCurved: true,
                  color: Theme.of(context).colorScheme.primary,
                  barWidth: 2,
                  dotData: const FlDotData(show: false),
                  belowBarData: BarAreaData(
                    show: true,
                    color: Theme.of(context).colorScheme.primary.withValues(alpha: 0.12),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildRangeSelector() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      child: Row(
        children: ['Today', 'Week', 'Month', 'Year'].map((label) => Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 3),
            child: ChoiceChip(
              label: Text(label, style: const TextStyle(fontSize: 12)),
              selected: _range == label,
              onSelected: (_) => _setRange(label),
            ),
          ),
        )).toList(),
      ),
    );
  }

  Future<void> _openSheet(List<Map<String, dynamic>> rows, bool isBuy) async {
    final price = rows.isNotEmpty && rows.first['pa'] != null
        ? (rows.first['pa'] as num).toDouble()
        : 0.0;
    final result = await showBuySellSheet(context, widget.name, price, isBuy: isBuy);
    if (result) _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _future,
      builder: (ctx, snap) {
        final rows = snap.data ?? [];
        return Scaffold(
          appBar: AppBar(title: Text(widget.name)),
          floatingActionButton: snap.hasData && rows.isNotEmpty
              ? Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    FloatingActionButton.small(
                      heroTag: 'sell',
                      backgroundColor: Colors.red,
                      onPressed: () => _openSheet(rows, false),
                      child: const Icon(Icons.remove),
                    ),
                    const SizedBox(height: 8),
                    FloatingActionButton.small(
                      heroTag: 'buy',
                      backgroundColor: Colors.green,
                      onPressed: () => _openSheet(rows, true),
                      child: const Icon(Icons.add),
                    ),
                  ],
                )
              : null,
          body: () {
            if (snap.hasError) {
              return Center(
                child: Column(mainAxisSize: MainAxisSize.min, children: [
                  const Icon(Icons.error_outline, size: 48, color: Colors.red),
                  const SizedBox(height: 12),
                  Text('${snap.error}', textAlign: TextAlign.center),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: _refresh, child: const Text('Retry')),
                ]),
              );
            }
            if (!snap.hasData) return const Center(child: CircularProgressIndicator());
            return RefreshIndicator(
              onRefresh: () async => _refresh(),
              child: ListView(
                children: [
                  _buildChart(rows),
                  _buildRangeSelector(),
                  const Divider(),
                  ...rows.map((r) => ListTile(
                    title: Text('${r['date']?.toString().substring(0, 10) ?? ''} — PA ${r['pa']}'),
                    subtitle: Text('PER ${r['per']?.toStringAsFixed(2) ?? '-'}  '
                        'PEG ${r['peg']?.toStringAsFixed(2) ?? '-'}  '
                        'PR ${r['pr']?.toStringAsFixed(2) ?? '-'}  '
                        'PB ${r['pb']?.toStringAsFixed(2) ?? '-'}'),
                  )),
                ],
              ),
            );
          }(),
        );
      },
    );
  }
}
