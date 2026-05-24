import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import '../main.dart' show kAccent, kBorder, kNegative, kPositive, kSurface, kSurfaceHigh, kTextMuted, kTextPrimary;

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
    try {
    print('DEBUG stats: getting user...');
    final me = await account.get();
    final userId = me.$id;
    print('DEBUG stats: user=$userId');

    final dataRes = await databases.listDocuments(
      databaseId: dbId,
      collectionId: 'data',
      queries: [Query.orderDesc('date'), Query.limit(500)],
    );
    print('DEBUG stats: got ${dataRes.documents.length} data docs');
    final latest = <String, Map<String, dynamic>>{};
    for (final d in dataRes.documents) {
      final n = d.data['c_name'] as String?;
      if (n != null && !latest.containsKey(n)) latest[n] = d.data;
    }
    final counts = {'green': 0, 'orange': 0, 'red': 0, 'total': latest.length};
    for (final r in latest.values) {
      final k = r['per_rating'] as String?;
      if (k != null && counts.containsKey(k)) counts[k] = counts[k]! + 1;
    }

    final ventesRes = await databases.listDocuments(
      databaseId: dbId,
      collectionId: 'ventes',
      queries: [Query.equal('user_id', userId), Query.limit(500)],
    );
    final achatsRes = await databases.listDocuments(
      databaseId: dbId,
      collectionId: 'achats',
      queries: [Query.equal('user_id', userId), Query.limit(500)],
    );

    final buyMap = <String, List<Map<String, dynamic>>>{};
    for (final d in achatsRes.documents) {
      final name = d.data['c_name'] as String? ?? '';
      buyMap.putIfAbsent(name, () => []).add(d.data);
    }

    final gains = <Map<String, dynamic>>[];
    for (final d in ventesRes.documents) {
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
    } catch (e, st) {
      print('DEBUG stats ERROR: $e');
      print('DEBUG stats STACK: $st');
      rethrow;
    }
  }

  Widget _perRatingCard(String label, int count, Color color) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 3),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: kSurface,
        borderRadius: BorderRadius.circular(10),
        border: Border(
          left: BorderSide(color: color, width: 3),
          top: const BorderSide(color: kBorder),
          right: const BorderSide(color: kBorder),
          bottom: const BorderSide(color: kBorder),
        ),
      ),
      child: Row(children: [
        Text(label, style: GoogleFonts.inter(color: kTextMuted, fontSize: 13)),
        const Spacer(),
        Text('$count', style: GoogleFonts.inter(
          color: color, fontSize: 18, fontWeight: FontWeight.w700)),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return RefreshIndicator(
      color: kAccent,
      onRefresh: () {
        final f = _load();
        setState(() => _future = f);
        return f;
      },
      child: FutureBuilder<Map<String, dynamic>>(
        future: _future,
        builder: (ctx, snap) {
          if (snap.hasError) {
            return ListView(children: [
              SizedBox(
                height: MediaQuery.of(ctx).size.height * 0.8,
                child: Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                  const Icon(Icons.error_outline, size: 48, color: kNegative),
                  const SizedBox(height: 16),
                  Text('Error: ${snap.error}', textAlign: TextAlign.center, style: const TextStyle(color: kTextMuted)),
                  const SizedBox(height: 16),
                  ElevatedButton(onPressed: () => setState(() => _future = _load()), child: const Text('Retry')),
                ])),
              ),
            ]);
          }
          if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: kAccent));

          final counts = snap.data!['counts'] as Map<String, dynamic>;
          final gains = snap.data!['gains'] as List<Map<String, dynamic>>;
          final totalGain = snap.data!['totalGain'] as double;
          final taxOwed = snap.data!['taxOwed'] as double;

          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              // Market overview card
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: kSurface,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: kBorder),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Market Overview', style: GoogleFonts.inter(
                    color: kTextMuted, fontSize: 12, fontWeight: FontWeight.w500)),
                  const SizedBox(height: 8),
                  Text('${counts['total']} stocks tracked', style: GoogleFonts.inter(
                    color: kTextPrimary, fontSize: 22, fontWeight: FontWeight.w700)),
                ]),
              ),
              const SizedBox(height: 16),
              Text('PER Ratings', style: GoogleFonts.inter(
                color: kTextMuted, fontSize: 12, fontWeight: FontWeight.w500)),
              const SizedBox(height: 8),
              _perRatingCard('Undervalued (green)', counts['green'] as int, kPositive),
              _perRatingCard('Fair value (orange)', counts['orange'] as int, const Color(0xFFE3A008)),
              _perRatingCard('Overvalued (red)', counts['red'] as int, kNegative),
              const SizedBox(height: 20),
              const Divider(height: 1),
              const SizedBox(height: 16),
              Row(children: [
                Text('Realized Gains', style: GoogleFonts.inter(
                  color: kTextPrimary, fontSize: 16, fontWeight: FontWeight.w600)),
              ]),
              const SizedBox(height: 8),
              if (gains.isEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Center(child: Text('No transactions yet',
                    style: GoogleFonts.inter(color: kTextMuted))),
                )
              else
                ...gains.map((g) {
                  final gain = g['gain'] as double;
                  final isPos = gain >= 0;
                  final color = isPos ? kPositive : kNegative;
                  final date = (g['date']?.toString() ?? '');
                  final dateShort = date.length >= 10 ? date.substring(0, 10) : date;
                  return Container(
                    margin: const EdgeInsets.symmetric(vertical: 3),
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                    decoration: BoxDecoration(
                      color: kSurface,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: kBorder),
                    ),
                    child: Row(children: [
                      Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text(g['c_name'] as String, style: GoogleFonts.inter(
                          color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w600)),
                        if (dateShort.isNotEmpty) ...[
                          const SizedBox(height: 2),
                          Text(dateShort, style: GoogleFonts.inter(color: kTextMuted, fontSize: 11)),
                        ],
                      ])),
                      Text(
                        '${isPos ? '+' : ''}${gain.toStringAsFixed(2)} MAD',
                        style: GoogleFonts.inter(color: color, fontSize: 14, fontWeight: FontWeight.w700),
                      ),
                    ]),
                  );
                }),
              const SizedBox(height: 16),
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: kSurfaceHigh,
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: kBorder),
                ),
                child: Row(children: [
                  Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('Total gain', style: GoogleFonts.inter(color: kTextMuted, fontSize: 12)),
                    const SizedBox(height: 4),
                    Text(
                      '${totalGain >= 0 ? '+' : ''}${totalGain.toStringAsFixed(2)} MAD',
                      style: GoogleFonts.inter(
                        color: totalGain >= 0 ? kPositive : kNegative,
                        fontSize: 20, fontWeight: FontWeight.w700),
                    ),
                  ])),
                  Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                    Text('Tax (15%)', style: GoogleFonts.inter(color: kTextMuted, fontSize: 12)),
                    const SizedBox(height: 4),
                    Text('${taxOwed.toStringAsFixed(2)} MAD',
                      style: GoogleFonts.inter(color: kTextMuted, fontSize: 14, fontWeight: FontWeight.w600)),
                  ]),
                ]),
              ),
              const SizedBox(height: 16),
            ],
          );
        },
      ),
    );
  }
}
