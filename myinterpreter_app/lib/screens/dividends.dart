import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import '../dividends.dart';
import '../main.dart'
    show kAccent, kBorder, kNegative, kPositive, kSurface, kSurfaceHigh, kTextMuted, kTextPrimary;
import 'stock_detail.dart';

/// Dividend calendar: who pays, when, and how much.
///
/// Two views on the same data — "Mes titres" filters to the user's holdings and
/// totals the income, "Marché" shows every issuer. The holdings view is the one
/// worth opening; the market view is for shopping.
class DividendsScreen extends StatefulWidget {
  const DividendsScreen({super.key});
  @override
  State<DividendsScreen> createState() => _DividendsScreenState();
}

class _DividendsScreenState extends State<DividendsScreen> {
  late Future<_DivData> _future;
  bool _mineOnly = true;

  @override
  void initState() {
    super.initState();
    _future = _load();
  }

  Future<_DivData> _load() async {
    final year = DateTime.now().year;
    final divs = await dividendsForYear(year);

    // Holdings are optional — a logged-out or empty portfolio still gets the
    // market view rather than an error.
    var qty = <String, double>{};
    try {
      final me = await account.get();
      final res = await databases.listDocuments(
        databaseId: dbId,
        collectionId: 'portefeuille',
        queries: [Query.equal('user_id', me.$id), Query.limit(200)],
      );
      for (final d in res.documents) {
        final n = d.data['c_name'] as String?;
        final q = (d.data['quantity'] as num?)?.toDouble() ?? 0;
        // Two lots of the same stock are one payment, not two.
        if (n != null) qty[n] = (qty[n] ?? 0) + q;
      }
    } catch (_) {/* no portfolio: market view only */}

    final prices = <String, double>{};
    try {
      final res = await databases.listDocuments(
        databaseId: dbId,
        collectionId: 'latest_prices',
        queries: [Query.limit(200)],
      );
      for (final d in res.documents) {
        final n = d.data['c_name'] as String?;
        if (n != null) prices[n] = (d.data['pa'] as num?)?.toDouble() ?? 0;
      }
    } catch (_) {}

    // Estimate ex-dates for issuers whose date is not yet announced. Only for
    // the user's own holdings — one query per company is too many for all 61.
    final forecasts = <String, DividendForecast>{};
    for (final d in divs) {
      if (d.confirmed || !qty.containsKey(d.cName)) continue;
      if (forecasts.containsKey(d.cName)) continue;
      try {
        final f = forecastExDate(await dividendsForCompany(d.cName), year);
        if (f != null) forecasts[d.cName] = f;
      } catch (_) {}
    }

    return _DivData(year: year, all: divs, qty: qty, prices: prices, forecasts: forecasts);
  }

  @override
  Widget build(BuildContext context) => FutureBuilder<_DivData>(
        future: _future,
        builder: (ctx, snap) {
          if (snap.hasError) {
            return _errorState('${snap.error}');
          }
          if (!snap.hasData) {
            return const Center(child: CircularProgressIndicator(color: kAccent));
          }
          final data = snap.data!;
          final today = todayIso();

          final rows = _mineOnly
              ? data.all.where((d) => data.qty.containsKey(d.cName)).toList()
              : List<Dividend>.from(data.all);
          rows.sort((a, b) =>
              (a.sortDate ?? '9999-99-99').compareTo(b.sortDate ?? '9999-99-99'));

          final upcoming = rows.where((d) => d.isUpcoming(today)).toList();
          final past = rows.where((d) => !d.isUpcoming(today)).toList();

          double total = 0, ahead = 0;
          for (final d in rows) {
            final q = data.qty[d.cName];
            if (q == null || d.amount == null) continue;
            final gross = d.amount! * q;
            total += gross;
            if (d.isUpcoming(today)) ahead += gross;
          }

          return RefreshIndicator(
            color: kAccent,
            onRefresh: () {
              setState(() => _future = _load());
              return _future;
            },
            child: ListView(
              padding: const EdgeInsets.only(top: 8, bottom: 24),
              children: [
                _toggle(data),
                if (_mineOnly && data.qty.isNotEmpty) _incomeCard(data.year, total, ahead),
                if (!_mineOnly) _cycleCard(),
                if (rows.isEmpty)
                  Padding(
                    padding: const EdgeInsets.all(32),
                    child: Column(children: [
                      const Icon(Icons.savings_outlined, size: 44, color: kTextMuted),
                      const SizedBox(height: 12),
                      Text(
                        _mineOnly
                            ? 'Aucun de vos titres ne verse de dividende en ${data.year}.'
                            : 'Aucun dividende enregistré.',
                        textAlign: TextAlign.center,
                        style: GoogleFonts.inter(color: kTextMuted, fontSize: 14),
                      ),
                    ]),
                  ),
                if (upcoming.isNotEmpty) _sectionTitle('À venir', upcoming.length),
                ...upcoming.map((d) => _card(d, data, dim: false)),
                if (past.isNotEmpty) _sectionTitle('Déjà versés', past.length),
                ...past.map((d) => _card(d, data, dim: true)),
                _footnote(data.year),
              ],
            ),
          );
        },
      );

  // ── Pieces ────────────────────────────────────────────────────────────────

  Widget _toggle(_DivData data) => Container(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: kBorder),
        ),
        child: Row(children: [
          _toggleBtn('Mes titres', true, data.qty.isNotEmpty),
          _toggleBtn('Marché (${data.all.length})', false, true),
        ]),
      );

  Widget _toggleBtn(String label, bool mine, bool enabled) => Expanded(
        child: GestureDetector(
          onTap: enabled ? () => setState(() => _mineOnly = mine) : null,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 10),
            decoration: BoxDecoration(
              color: _mineOnly == mine ? kAccent.withValues(alpha: 0.15) : Colors.transparent,
              borderRadius: BorderRadius.circular(9),
            ),
            child: Text(
              label,
              textAlign: TextAlign.center,
              style: GoogleFonts.inter(
                color: !enabled
                    ? kTextMuted.withValues(alpha: 0.4)
                    : (_mineOnly == mine ? kAccent : kTextMuted),
                fontSize: 13,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ),
      );

  Widget _incomeCard(int year, double total, double ahead) => Container(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: kSurfaceHigh,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: kBorder),
        ),
        child: Row(children: [
          _col('Revenus $year', '${total.toStringAsFixed(2)} MAD', kPositive),
          Container(width: 1, height: 32, color: kBorder),
          _col('Encore à venir', '${ahead.toStringAsFixed(2)} MAD', kAccent),
        ]),
      );

  Widget _col(String label, String value, Color c) => Expanded(
        child: Column(children: [
          Text(label, style: GoogleFonts.inter(color: kTextMuted, fontSize: 11)),
          const SizedBox(height: 4),
          Text(value,
              style: GoogleFonts.inter(color: c, fontSize: 15, fontWeight: FontWeight.w700)),
        ]),
      );

  /// The Moroccan cycle, explained once so "estimé" rows have context.
  Widget _cycleCard() => Container(
        margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: kSurface,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: kBorder),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Icon(Icons.event_available, size: 15, color: kPositive),
            const SizedBox(width: 6),
            Text('Le cycle du dividende',
                style: GoogleFonts.inter(
                    color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
          ]),
          const SizedBox(height: 8),
          _cycleStep('31 déc.', "Clôture de l'exercice"),
          _cycleStep('mars – avril', 'Le conseil propose le dividende'),
          _cycleStep('avril – mai', "L'assemblée générale le vote"),
          _cycleStep('mai – sept.', 'Détachement puis paiement', highlight: true),
          const SizedBox(height: 8),
          Text(
            '95 % des versements tombent entre mai et septembre, avec un pic net '
            'en juillet. Les dates exactes changent chaque année.',
            style: GoogleFonts.inter(color: kTextMuted, fontSize: 11, height: 1.5),
          ),
        ]),
      );

  Widget _cycleStep(String when, String what, {bool highlight = false}) => Padding(
        padding: const EdgeInsets.only(top: 4),
        child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(
            width: 84,
            child: Text(when,
                style: GoogleFonts.robotoMono(
                    color: highlight ? kPositive : kAccent,
                    fontSize: 11,
                    fontWeight: FontWeight.w700)),
          ),
          Expanded(
            child: Text(what, style: GoogleFonts.inter(color: kTextMuted, fontSize: 11)),
          ),
        ]),
      );

  Widget _sectionTitle(String label, int n) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 6),
        child: Text('${label.toUpperCase()}  ·  $n',
            style: GoogleFonts.inter(
                color: kTextMuted, fontSize: 11, fontWeight: FontWeight.w700, letterSpacing: 1.1)),
      );

  Widget _card(Dividend d, _DivData data, {required bool dim}) {
    final qty = data.qty[d.cName];
    final gross = (qty != null && d.amount != null) ? d.amount! * qty : null;
    final yld = d.yieldOn(data.prices[d.cName]);
    final forecast = data.forecasts[d.cName];
    final opacity = dim ? 0.5 : 1.0;

    return Opacity(
      opacity: opacity,
      child: GestureDetector(
        onTap: () => Navigator.push(context,
            MaterialPageRoute(builder: (_) => StockDetailScreen(name: d.cName))),
        child: Container(
          margin: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
          decoration: BoxDecoration(
            color: kSurface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: kBorder),
          ),
          child: Column(children: [
            Row(children: [
              Expanded(
                child: Text(d.cName,
                    style: GoogleFonts.inter(
                        color: kTextPrimary, fontSize: 14, fontWeight: FontWeight.w600)),
              ),
              if (d.amount != null)
                Text('${d.amount!.toStringAsFixed(2)} MAD',
                    style: GoogleFonts.inter(
                        color: kTextPrimary, fontSize: 13, fontWeight: FontWeight.w700)),
            ]),
            const SizedBox(height: 6),
            Row(children: [
              _chip(
                d.confirmed
                    ? 'confirmé'
                    : (forecast != null ? 'estimé' : 'prévu'),
                d.confirmed ? kPositive : kAccent,
              ),
              if (d.isQuarterly) _chip('trimestriel', kTextMuted),
              if (d.isExceptional) _chip('exceptionnel', kAccent),
              const Spacer(),
              if (yld != null)
                Text('${yld.toStringAsFixed(2)} %',
                    style: GoogleFonts.inter(color: kPositive, fontSize: 12)),
            ]),
            const SizedBox(height: 8),
            _row('Détachement',
                d.exDate != null
                    ? fmtDate(d.exDate)
                    : (forecast != null ? '≈ ${fmtForecastWindow(forecast)}' : '—'),
                estimated: d.exDate == null && forecast != null),
            _row('Paiement', fmtPayment(d)),
            if (gross != null)
              _row('Vous recevrez', '${gross.toStringAsFixed(2)} MAD  (${qty!.toStringAsFixed(0)} titres)',
                  strong: true),
            if (!d.confirmed && forecast != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  'Estimation sur ${forecast.years} années, dates variant de '
                  '${forecast.spread} jours. Pas un engagement — vérifié sur '
                  "l'an dernier, elle tombe juste 8 fois sur 10.",
                  style: GoogleFonts.inter(color: kTextMuted, fontSize: 10, height: 1.45),
                ),
              ),
          ]),
        ),
      ),
    );
  }

  Widget _chip(String label, Color c) => Container(
        margin: const EdgeInsets.only(right: 6),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: c.withValues(alpha: 0.13),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: c.withValues(alpha: 0.35)),
        ),
        child: Text(label,
            style: GoogleFonts.inter(color: c, fontSize: 10, fontWeight: FontWeight.w700)),
      );

  Widget _row(String label, String value, {bool strong = false, bool estimated = false}) =>
      Padding(
        padding: const EdgeInsets.only(top: 3),
        child: Row(children: [
          Expanded(
              child: Text(label, style: GoogleFonts.inter(color: kTextMuted, fontSize: 11))),
          Text(value,
              style: GoogleFonts.inter(
                color: strong ? kPositive : (estimated ? kAccent : kTextPrimary),
                fontSize: 11,
                fontWeight: strong ? FontWeight.w700 : FontWeight.w500,
              )),
        ]),
      );

  Widget _footnote(int year) => Padding(
        padding: const EdgeInsets.fromLTRB(18, 18, 18, 8),
        child: Text(
          'Montants bruts, avant retenue à la source. Le dividende versé en $year '
          "provient de l'exercice ${year - 1}. Calendrier actualisé chaque semaine.",
          style: GoogleFonts.inter(color: kTextMuted, fontSize: 10, height: 1.5),
        ),
      );

  Widget _errorState(String msg) => Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Icon(Icons.error_outline, size: 48, color: kNegative),
            const SizedBox(height: 12),
            Text(msg,
                style: const TextStyle(color: kTextMuted), textAlign: TextAlign.center),
            const SizedBox(height: 12),
            ElevatedButton(
              onPressed: () => setState(() => _future = _load()),
              child: const Text('Réessayer'),
            ),
          ]),
        ),
      );
}

class _DivData {
  final int year;
  final List<Dividend> all;
  final Map<String, double> qty;
  final Map<String, double> prices;
  final Map<String, DividendForecast> forecasts;
  const _DivData({
    required this.year,
    required this.all,
    required this.qty,
    required this.prices,
    required this.forecasts,
  });
}
