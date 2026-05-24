import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';
import '../main.dart' show kBorder, kNegative, kPositive, kSurface, kTextMuted, kTextPrimary;

Future<bool> showBuySellSheet(
  BuildContext context,
  String cName,
  double defaultPrice, {
  bool isBuy = true,
}) async {
  final result = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
    backgroundColor: kSurface,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
    ),
    builder: (ctx) => _BuySellSheet(cName: cName, defaultPrice: defaultPrice, isBuy: isBuy),
  );
  return result ?? false;
}

class _BuySellSheet extends StatefulWidget {
  final String cName;
  final double defaultPrice;
  final bool isBuy;
  const _BuySellSheet({required this.cName, required this.defaultPrice, required this.isBuy});
  @override
  State<_BuySellSheet> createState() => _BuySellSheetState();
}

class _BuySellSheetState extends State<_BuySellSheet> {
  final _qtyCtrl = TextEditingController();
  final _priceCtrl = TextEditingController();
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _priceCtrl.text = widget.defaultPrice.toStringAsFixed(2);
  }

  @override
  void dispose() {
    _qtyCtrl.dispose();
    _priceCtrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    final qty = double.tryParse(_qtyCtrl.text);
    final price = double.tryParse(_priceCtrl.text);
    if (qty == null || qty <= 0 || price == null || price <= 0) {
      setState(() => _error = 'Enter valid quantity and price');
      return;
    }
    setState(() { _loading = true; _error = null; });
    try {
      final me = await account.get();
      final userId = me.$id;
      final now = DateTime.now().toUtc().toIso8601String();

      if (widget.isBuy) {
        await databases.createDocument(
          databaseId: dbId,
          collectionId: 'achats',
          documentId: ID.unique(),
          permissions: [Permission.read(Role.user(userId)), Permission.write(Role.user(userId))],
          data: {'user_id': userId, 'c_name': widget.cName, 'quantity': qty, 'price': price, 'date': now},
        );
        final existing = await databases.listDocuments(
          databaseId: dbId,
          collectionId: 'portefeuille',
          queries: [Query.equal('user_id', userId), Query.equal('c_name', widget.cName), Query.limit(1)],
        );
        if (existing.documents.isEmpty) {
          await databases.createDocument(
            databaseId: dbId,
            collectionId: 'portefeuille',
            documentId: ID.unique(),
            permissions: [Permission.read(Role.user(userId)), Permission.write(Role.user(userId))],
            data: {'user_id': userId, 'c_name': widget.cName, 'quantity': qty, 'total_cost': qty * price},
          );
        } else {
          final doc = existing.documents.first;
          final oldQty = (doc.data['quantity'] as num?)?.toDouble() ?? 0;
          final oldCost = (doc.data['total_cost'] as num?)?.toDouble() ?? 0;
          await databases.updateDocument(
            databaseId: dbId,
            collectionId: 'portefeuille',
            documentId: doc.$id,
            data: {'quantity': oldQty + qty, 'total_cost': oldCost + qty * price},
          );
        }
      } else {
        final existing = await databases.listDocuments(
          databaseId: dbId,
          collectionId: 'portefeuille',
          queries: [Query.equal('user_id', userId), Query.equal('c_name', widget.cName), Query.limit(1)],
        );
        if (existing.documents.isEmpty) throw Exception('No holdings for ${widget.cName}');
        final doc = existing.documents.first;
        final oldQty = (doc.data['quantity'] as num?)?.toDouble() ?? 0;
        if (oldQty <= 0) throw Exception('Invalid holding quantity');
        if (qty > oldQty) throw Exception('Cannot sell more than held ($oldQty)');

        await databases.createDocument(
          databaseId: dbId,
          collectionId: 'ventes',
          documentId: ID.unique(),
          permissions: [Permission.read(Role.user(userId)), Permission.write(Role.user(userId))],
          data: {'user_id': userId, 'c_name': widget.cName, 'quantity': qty, 'price': price, 'date': now},
        );
        final newQty = oldQty - qty;
        final oldCost = (doc.data['total_cost'] as num?)?.toDouble() ?? 0;
        final newCost = oldCost * (newQty / oldQty);
        if (newQty <= 0) {
          await databases.deleteDocument(databaseId: dbId, collectionId: 'portefeuille', documentId: doc.$id);
        } else {
          await databases.updateDocument(
            databaseId: dbId,
            collectionId: 'portefeuille',
            documentId: doc.$id,
            data: {'quantity': newQty, 'total_cost': newCost},
          );
        }
      }
      if (mounted) Navigator.pop(context, true);
    } catch (e) {
      setState(() { _error = e.toString(); _loading = false; });
    }
  }

  @override
  Widget build(BuildContext context) {
    final actionColor = widget.isBuy ? kPositive : kNegative;
    return Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 24,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        // handle bar
        Center(
          child: Container(
            width: 36, height: 4,
            margin: const EdgeInsets.only(bottom: 20),
            decoration: BoxDecoration(
              color: kBorder, borderRadius: BorderRadius.circular(2)),
          ),
        ),
        Row(children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: actionColor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Icon(widget.isBuy ? Icons.trending_up : Icons.trending_down,
              color: actionColor, size: 20),
          ),
          const SizedBox(width: 12),
          Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(
              widget.isBuy ? 'Buy' : 'Sell',
              style: GoogleFonts.inter(color: kTextMuted, fontSize: 12),
            ),
            Text(widget.cName, style: GoogleFonts.inter(
              color: kTextPrimary, fontSize: 18, fontWeight: FontWeight.w700)),
          ])),
        ]),
        const SizedBox(height: 24),
        TextField(
          controller: _qtyCtrl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Quantity'),
        ),
        const SizedBox(height: 12),
        TextField(
          controller: _priceCtrl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Price (MAD)'),
        ),
        if (_error != null) ...[
          const SizedBox(height: 10),
          Text(_error!, style: GoogleFonts.inter(color: kNegative, fontSize: 13)),
        ],
        const SizedBox(height: 20),
        SizedBox(
          height: 48,
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: actionColor,
              foregroundColor: Colors.white,
            ),
            onPressed: _loading ? null : _submit,
            child: _loading
                ? const SizedBox(height: 20, width: 20,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : Text(widget.isBuy ? 'Confirm Buy' : 'Confirm Sell',
                    style: GoogleFonts.inter(fontWeight: FontWeight.w600)),
          ),
        ),
      ]),
    );
  }
}
