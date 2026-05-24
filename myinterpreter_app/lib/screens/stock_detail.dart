import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import 'package:fl_chart/fl_chart.dart';
import '../appwrite_client.dart';
import '../main.dart' show kAccent, kBorder, kNegative, kPositive, kSurface, kSurfaceHigh, kTextMuted;
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
    try {
    final now = DateTime.now();
    final cutoff = switch (_range) {
      'Today' => DateTime(now.year, now.month, now.day),
      'Week'  => now.subtract(const Duration(days: 7)),
      'Month' => now.subtract(const Duration(days: 30)),
      _       => DateTime(now.year - 1, now.month, now.day),
    };
    final cutoffStr = cutoff.toUtc().toIso8601String();
    final res = await databases.listDocuments(
      databaseId: dbId,
      collectionId: 'data',
      queries: [
        Query.equal('c_name', widget.name),
        Query.greaterThanEqual('date', cutoffStr),
        Query.orderDesc('date'),
        Query.limit(2000),
      ],
    );
    print('DEBUG detail: got ${res.documents.length} docs for ${widget.name}');
    if (res.documents.isNotEmpty) print('DEBUG detail first: ${res.documents.first.data}');
    return res.documents.map((d) => d.data).toList();
    } catch (e, st) {
      print('DEBUG detail ERROR: $e');
      print('DEBUG detail STACK: $st');
      rethrow;
    }
  }

  void _refresh() => setState(() => _future = _load());
  void _setRange(String range) => setState(() { _range = range; _future = _load(); });

  Widget _buildChart(List<Map<String, dynamic>> rows) {
    if (rows.isEmpty) {
      return SizedBox(
        height: 220,
        child: Center(child: Text('No data for this range',
          style: GoogleFonts.inter(color: kTextMuted))),
      );
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

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      padding: const EdgeInsets.fromLTRB(8, 16, 16, 8),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: kBorder),
      ),
      child: SizedBox(
        height: 220,
        child: LineChart(
          LineChartData(
            minX: 0,
            maxX: (spots.length - 1).toDouble(),
            minY: minY - padding,
            maxY: maxY + padding,
            gridData: FlGridData(
              show: true,
              drawVerticalLine: false,
              getDrawingHorizontalLine: (_) => const FlLine(color: kBorder, strokeWidth: 1),
            ),
            borderData: FlBorderData(show: false),
            titlesData: FlTitlesData(
              leftTitles: AxisTitles(
                sideTitles: SideTitles(
                  showTitles: true,
                  reservedSize: 52,
                  getTitlesWidget: (v, _) => Text(v.toStringAsFixed(0),
                    style: GoogleFonts.inter(color: kTextMuted, fontSize: 10)),
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
                      child: Text(labelAt(idx),
                        style: GoogleFonts.inter(color: kTextMuted, fontSize: 9)),
                    );
                  },
                ),
              ),
              topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
              rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            ),
            lineTouchData: LineTouchData(
              touchTooltipData: LineTouchTooltipData(
                tooltipRoundedRadius: 8,
                tooltipBorder: const BorderSide(color: kBorder),
                getTooltipItems: (spots) => spots.map((s) {
                  final idx = s.x.round();
                  final date = idx < reversed.length ? labelAt(idx) : '';
                  return LineTooltipItem('$date\n${s.y.toStringAsFixed(2)} MAD',
                    GoogleFonts.inter(fontSize: 12, color: kAccent, fontWeight: FontWeight.w600));
                }).toList(),
              ),
            ),
            lineBarsData: [
              LineChartBarData(
                spots: spots,
                isCurved: true,
                color: kAccent,
                barWidth: 2,
                dotData: const FlDotData(show: false),
                belowBarData: BarAreaData(
                  show: true,
                  color: kAccent.withValues(alpha: 0.10),
                ),
              ),
            ],
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
              label: Text(label),
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
                      backgroundColor: kNegative,
                      foregroundColor: Colors.white,
                      onPressed: () => _openSheet(rows, false),
                      child: const Icon(Icons.remove),
                    ),
                    const SizedBox(height: 8),
                    FloatingActionButton.small(
                      heroTag: 'buy',
                      backgroundColor: kPositive,
                      foregroundColor: Colors.white,
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
                  const Icon(Icons.error_outline, size: 48, color: kNegative),
                  const SizedBox(height: 12),
                  Text('${snap.error}', textAlign: TextAlign.center,
                    style: const TextStyle(color: kTextMuted)),
                  const SizedBox(height: 12),
                  ElevatedButton(onPressed: _refresh, child: const Text('Retry')),
                ]),
              );
            }
            if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: kAccent));
            return RefreshIndicator(
              color: kAccent,
              onRefresh: () { _refresh(); return Future.value(); },
              child: ListView(
                children: [
                  _buildChart(rows),
                  _buildRangeSelector(),
                  const Divider(height: 16),
                  ...rows.map((r) {
                    final date = (r['date']?.toString() ?? '');
                    final dateShort = date.length >= 10 ? date.substring(0, 10) : date;
                    return Container(
                      margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 3),
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: kSurface,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: kBorder),
                      ),
                      child: Row(children: [
                        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text(dateShort, style: GoogleFonts.inter(
                            color: kTextMuted, fontSize: 12)),
                          const SizedBox(height: 2),
                          Text(
                            'PER ${r['per']?.toStringAsFixed(2) ?? '-'}  '
                            'PEG ${r['peg']?.toStringAsFixed(2) ?? '-'}  '
                            'PR ${r['pr']?.toStringAsFixed(2) ?? '-'}  '
                            'PB ${r['pb']?.toStringAsFixed(2) ?? '-'}',
                            style: GoogleFonts.inter(color: kTextMuted, fontSize: 11),
                          ),
                        ])),
                        Text(
                          r['pa'] != null ? '${r['pa']} MAD' : '—',
                          style: GoogleFonts.inter(
                            color: kAccent, fontSize: 14, fontWeight: FontWeight.w700),
                        ),
                      ]),
                    );
                  }),
                  const SizedBox(height: 80),
                ],
              ),
            );
          }(),
        );
      },
    );
  }
}
