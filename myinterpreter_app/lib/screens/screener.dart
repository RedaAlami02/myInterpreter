import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import '../main.dart' show kAccent, kBorder, kNegative, kPositive, kSurface, kTextMuted, kTextPrimary;
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
    try {
      final res = await databases.listDocuments(
        databaseId: dbId,
        collectionId: 'data',
        queries: [Query.orderDesc('date'), Query.limit(500)],
      );
      final latest = <String, Map<String, dynamic>>{};
      for (final d in res.documents) {
        final name = d.data['c_name'] as String?;
        if (name != null && !latest.containsKey(name)) latest[name] = d.data;
      }
      return latest.values.toList();
    } catch (e, st) {
      print('ERROR screener: $e\n$st');
      rethrow;
    }
  }

  List<Map<String, dynamic>> _filter(List<Map<String, dynamic>> rows) {
    final q = _search.text.toLowerCase();
    if (q.isEmpty) return rows;
    return rows.where((r) => (r['c_name'] as String? ?? '').toLowerCase().contains(q)).toList();
  }

  Color _ratingColor(String? r) => switch (r) {
    'green'  => kPositive,
    'orange' => const Color(0xFFE3A008),
    'red'    => kNegative,
    _        => kBorder,
  };

  @override
  Widget build(BuildContext context) => FutureBuilder<List<Map<String, dynamic>>>(
    future: _future,
    builder: (ctx, snap) {
      if (snap.hasError) {
        return Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.error_outline, size: 48, color: kNegative),
            const SizedBox(height: 12),
            Text('${snap.error}', style: const TextStyle(color: kTextMuted), textAlign: TextAlign.center),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: () => setState(() => _future = _loadLatest()),
              child: const Text('Retry'),
            ),
          ]),
        );
      }
      if (!snap.hasData) return const Center(child: CircularProgressIndicator(color: kAccent));
      final rows = _filter(snap.data!);
      return Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 12, 12, 6),
            child: TextField(
              controller: _search,
              decoration: const InputDecoration(
                hintText: 'Search stocks...',
                prefixIcon: Icon(Icons.search, size: 18),
              ),
            ),
          ),
          Expanded(
            child: RefreshIndicator(
              color: kAccent,
              onRefresh: () {
                final f = _loadLatest();
                setState(() => _future = f);
                return f;
              },
              child: ListView.builder(
                padding: const EdgeInsets.only(top: 4, bottom: 16),
                itemCount: rows.length,
                itemBuilder: (_, i) => _StockCard(
                  row: rows[i],
                  ratingColor: _ratingColor,
                  onTap: () {
                    final name = rows[i]['c_name'] as String? ?? '';
                    if (name.isEmpty) return;
                    Navigator.push(context,
                      MaterialPageRoute(builder: (_) => StockDetailScreen(name: name)));
                  },
                  onBuy: () async {
                    final r = rows[i];
                    final name = r['c_name'] as String? ?? '';
                    final pa = (r['pa'] as num?)?.toDouble() ?? 0.0;
                    if (name.isEmpty) return;
                    await showBuySellSheet(context, name, pa, isBuy: true);
                    if (mounted) setState(() => _future = _loadLatest());
                  },
                ),
              ),
            ),
          ),
        ],
      );
    },
  );
}

class _StockCard extends StatelessWidget {
  final Map<String, dynamic> row;
  final Color Function(String?) ratingColor;
  final VoidCallback onTap;
  final VoidCallback onBuy;

  const _StockCard({
    required this.row,
    required this.ratingColor,
    required this.onTap,
    required this.onBuy,
  });

  Widget _badge(String label, String? rating) {
    final color = switch (rating) {
      'green'  => kPositive,
      'orange' => const Color(0xFFE3A008),
      'red'    => kNegative,
      _        => kBorder,
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.4), width: 1),
      ),
      child: Text(label, style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.w600)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final name = row['c_name'] as String? ?? '?';
    final pa = row['pa'];
    final per = row['per'];

    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: kBorder, width: 1),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(name, style: GoogleFonts.inter(
                    color: kTextPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 6),
                  Wrap(
                    spacing: 4,
                    runSpacing: 4,
                    children: [
                      _badge('PER', row['per_rating'] as String?),
                      _badge('PEG', row['peg_rating'] as String?),
                      _badge('PR',  row['pr_rating']  as String?),
                      _badge('PB',  row['pb_rating']  as String?),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(width: 12),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  pa != null ? '$pa MAD' : '—',
                  style: GoogleFonts.inter(
                    color: kAccent, fontSize: 15, fontWeight: FontWeight.w700),
                ),
                if (per != null) ...[
                  const SizedBox(height: 2),
                  Text(
                    'PER ${per.toStringAsFixed(1)}',
                    style: GoogleFonts.inter(color: kTextMuted, fontSize: 11),
                  ),
                ],
                const SizedBox(height: 8),
                GestureDetector(
                  onTap: onBuy,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: kAccent.withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(6),
                      border: Border.all(color: kAccent.withValues(alpha: 0.4)),
                    ),
                    child: const Icon(Icons.add_shopping_cart, size: 14, color: kAccent),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
