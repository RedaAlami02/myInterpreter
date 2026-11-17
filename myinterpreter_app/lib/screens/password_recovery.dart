import 'package:flutter/material.dart';

import '../backend_contract.dart';
import 'login.dart';

class PasswordRecoveryScreen extends StatefulWidget {
  final EmailAuthBackend auth;
  const PasswordRecoveryScreen({super.key, required this.auth});

  @override
  State<PasswordRecoveryScreen> createState() => _PasswordRecoveryScreenState();
}

class _PasswordRecoveryScreenState extends State<PasswordRecoveryScreen> {
  final _password = TextEditingController();
  final _confirmation = TextEditingController();
  String? _error;
  bool _busy = false;

  Future<void> _finish({required bool cancel}) async {
    if (_busy) return;
    if (!cancel && _password.text != _confirmation.text) {
      setState(() => _error = 'The passwords do not match.');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      if (cancel) {
        await widget.auth.cancelEmailRecovery();
      } else {
        await widget.auth.updateRecoveredPassword(_password.text);
      }
      _password.clear();
      _confirmation.clear();
      if (!mounted) return;
      _returnToLogin(
        cancel
            ? 'Password recovery cancelled.'
            : 'Password updated. Sign in with your new password.',
      );
    } catch (error) {
      if (mounted) {
        if (error is BackendFailure && error.signedOut) {
          _password.clear();
          _confirmation.clear();
          _returnToLogin(error.message);
          return;
        }
        setState(
          () => _error = error is BackendFailure
              ? error.message
              : 'Password recovery could not be completed. Please retry.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _returnToLogin(String notice) {
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute<void>(
        builder: (_) => LoginScreen(initialNotice: notice),
      ),
      (_) => false,
    );
  }

  @override
  void dispose() {
    _password.dispose();
    _confirmation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => PopScope(
    canPop: false,
    child: Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('Set a new password'),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Use 8–128 characters. You will sign in again after saving.',
              ),
              const SizedBox(height: 20),
              TextField(
                controller: _password,
                obscureText: true,
                enableSuggestions: false,
                autocorrect: false,
                decoration: const InputDecoration(labelText: 'New password'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _confirmation,
                obscureText: true,
                enableSuggestions: false,
                autocorrect: false,
                decoration: const InputDecoration(
                  labelText: 'Confirm new password',
                ),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: _busy ? null : () => _finish(cancel: false),
                child: const Text('Save password'),
              ),
              TextButton(
                onPressed: _busy ? null : () => _finish(cancel: true),
                child: const Text('Cancel recovery'),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
