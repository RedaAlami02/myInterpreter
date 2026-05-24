import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:appwrite/appwrite.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import '../appwrite_client.dart';
import '../main.dart' show kAccent, kBg, kNegative, kSurface, kBorder, kTextPrimary, kTextMuted;
import 'home.dart';

const _storage = FlutterSecureStorage();
const _kStayLoggedIn = 'stay_logged_in';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email    = TextEditingController();
  final _password = TextEditingController();
  final _name     = TextEditingController();
  String? _error;
  bool _loading      = false;
  bool _isSignUp     = false;
  bool _stayLoggedIn = true;

  Future<void> _submit() async {
    setState(() { _loading = true; _error = null; });
    try {
      if (_isSignUp) {
        await account.create(
          userId: ID.unique(),
          email: _email.text.trim(),
          password: _password.text,
          name: _name.text.trim().isEmpty ? null : _name.text.trim(),
        );
      }
      await account.createEmailPasswordSession(
        email: _email.text.trim(),
        password: _password.text,
      );
      await _storage.write(key: _kStayLoggedIn, value: _stayLoggedIn ? 'true' : 'false');
      if (!mounted) return;
      Navigator.pushReplacement(context,
        MaterialPageRoute(builder: (_) => const HomeScreen()));
    } on AppwriteException catch (e) {
      setState(() => _error = e.message ?? (_isSignUp ? 'Sign up failed' : 'Login failed'));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'myInterpreter',
                textAlign: TextAlign.center,
                style: GoogleFonts.inter(
                  color: kAccent, fontSize: 30,
                  fontWeight: FontWeight.w700, letterSpacing: -0.5),
              ),
              const SizedBox(height: 6),
              Text(
                'Bourse de Casablanca',
                textAlign: TextAlign.center,
                style: GoogleFonts.inter(color: kTextMuted, fontSize: 13),
              ),
              const SizedBox(height: 40),
              Container(
                padding: const EdgeInsets.all(24),
                decoration: BoxDecoration(
                  color: kSurface,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: kBorder),
                ),
                child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Text(
                    _isSignUp ? 'Create account' : 'Sign in',
                    style: GoogleFonts.inter(
                      color: kTextPrimary, fontSize: 18, fontWeight: FontWeight.w600)),
                  const SizedBox(height: 20),
                  if (_isSignUp) ...[
                    TextField(
                      controller: _name,
                      decoration: const InputDecoration(labelText: 'Name (optional)'),
                    ),
                    const SizedBox(height: 12),
                  ],
                  TextField(
                    controller: _email,
                    keyboardType: TextInputType.emailAddress,
                    decoration: const InputDecoration(labelText: 'Email'),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _password,
                    obscureText: true,
                    decoration: const InputDecoration(labelText: 'Password'),
                  ),
                  const SizedBox(height: 8),
                  // Stay logged in checkbox
                  Row(children: [
                    SizedBox(
                      width: 24, height: 24,
                      child: Checkbox(
                        value: _stayLoggedIn,
                        activeColor: kAccent,
                        checkColor: kBg,
                        side: const BorderSide(color: kTextMuted),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
                        onChanged: (v) => setState(() => _stayLoggedIn = v ?? true),
                      ),
                    ),
                    const SizedBox(width: 10),
                    GestureDetector(
                      onTap: () => setState(() => _stayLoggedIn = !_stayLoggedIn),
                      child: Text('Stay logged in',
                        style: GoogleFonts.inter(color: kTextMuted, fontSize: 13)),
                    ),
                  ]),
                  if (_error != null) ...[
                    const SizedBox(height: 12),
                    Text(_error!, style: TextStyle(color: kNegative, fontSize: 13)),
                  ],
                  const SizedBox(height: 16),
                  SizedBox(
                    height: 48,
                    child: ElevatedButton(
                      onPressed: _loading ? null : _submit,
                      child: _loading
                          ? const SizedBox(height: 20, width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2, color: kBg))
                          : Text(_isSignUp ? 'Sign up' : 'Log in'),
                    ),
                  ),
                  const SizedBox(height: 16),
                  // Toggle sign in / sign up
                  Row(mainAxisAlignment: MainAxisAlignment.center, children: [
                    Text(
                      _isSignUp ? 'Already have an account? ' : 'No account? ',
                      style: GoogleFonts.inter(color: kTextMuted, fontSize: 13),
                    ),
                    GestureDetector(
                      onTap: () => setState(() { _isSignUp = !_isSignUp; _error = null; }),
                      child: Text(
                        _isSignUp ? 'Sign in' : 'Sign up',
                        style: GoogleFonts.inter(
                          color: kAccent, fontSize: 13, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ]),
                ]),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
