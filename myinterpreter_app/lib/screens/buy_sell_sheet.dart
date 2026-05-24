import 'package:flutter/material.dart';
import 'package:appwrite/appwrite.dart';
import '../appwrite_client.dart';

Future<bool> showBuySellSheet(
  BuildContext context,
  String cName,
  double defaultPrice, {
  bool isBuy = true,
}) async {
  final result = await showModalBottomSheet<bool>(
    context: context,
    isScrollControlled: true,
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
        await tablesDB.createRow(
          databaseId: dbId,
          tableId: 'achats',
          rowId: ID.unique(),
          data: {'user_id': userId, 'c_name': widget.cName, 'quantity': qty, 'price': price, 'date': now},
        );
        final existing = await tablesDB.listRows(
          databaseId: dbId,
          tableId: 'portefeuille',
          queries: [Query.equal('user_id', userId), Query.equal('c_name', widget.cName), Query.limit(1)],
        );
        if (existing.rows.isEmpty) {
          await tablesDB.createRow(
            databaseId: dbId,
            tableId: 'portefeuille',
            rowId: ID.unique(),
            data: {'user_id': userId, 'c_name': widget.cName, 'quantity': qty, 'total_cost': qty * price},
          );
        } else {
          final row = existing.rows.first;
          final oldQty = (row.data['quantity'] as num).toDouble();
          final oldCost = (row.data['total_cost'] as num).toDouble();
          await tablesDB.updateRow(
            databaseId: dbId,
            tableId: 'portefeuille',
            rowId: row.$id,
            data: {'quantity': oldQty + qty, 'total_cost': oldCost + qty * price},
          );
        }
      } else {
        final existing = await tablesDB.listRows(
          databaseId: dbId,
          tableId: 'portefeuille',
          queries: [Query.equal('user_id', userId), Query.equal('c_name', widget.cName), Query.limit(1)],
        );
        if (existing.rows.isEmpty) throw Exception('No holdings for ${widget.cName}');
        final row = existing.rows.first;
        final oldQty = (row.data['quantity'] as num).toDouble();
        if (qty > oldQty) throw Exception('Cannot sell more than held ($oldQty)');

        await tablesDB.createRow(
          databaseId: dbId,
          tableId: 'ventes',
          rowId: ID.unique(),
          data: {'user_id': userId, 'c_name': widget.cName, 'quantity': qty, 'price': price, 'date': now},
        );
        final newQty = oldQty - qty;
        final oldCost = (row.data['total_cost'] as num).toDouble();
        final newCost = oldCost * (newQty / oldQty);
        if (newQty <= 0) {
          await tablesDB.deleteRow(databaseId: dbId, tableId: 'portefeuille', rowId: row.$id);
        } else {
          await tablesDB.updateRow(
            databaseId: dbId,
            tableId: 'portefeuille',
            rowId: row.$id,
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
    return Padding(
      padding: EdgeInsets.only(
        left: 16, right: 16, top: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 16,
      ),
      child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('${widget.isBuy ? 'Buy' : 'Sell'} ${widget.cName}',
          style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 16),
        TextField(controller: _qtyCtrl, keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Quantity', border: OutlineInputBorder())),
        const SizedBox(height: 12),
        TextField(controller: _priceCtrl, keyboardType: TextInputType.number,
          decoration: const InputDecoration(labelText: 'Price (MAD)', border: OutlineInputBorder())),
        if (_error != null) ...[
          const SizedBox(height: 8),
          Text(_error!, style: const TextStyle(color: Colors.red)),
        ],
        const SizedBox(height: 16),
        ElevatedButton(
          onPressed: _loading ? null : _submit,
          child: _loading ? const SizedBox(height: 20, width: 20, child: CircularProgressIndicator(strokeWidth: 2))
              : Text(widget.isBuy ? 'Buy' : 'Sell'),
        ),
      ]),
    );
  }
}
