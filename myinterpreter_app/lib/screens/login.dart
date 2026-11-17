import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../backend.dart';
import '../app_colors.dart'
    show kAccent, kBg, kNegative, kSurface, kBorder, kTextPrimary, kTextMuted;
import 'home.dart';

class LoginScreen extends StatefulWidget {
  final String? initialNotice;
  const LoginScreen({super.key, this.initialNotice});
  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _name = TextEditingController();
  String? _error;
  String? _notice;
  bool _loading = false;
  bool _isSignUp = false;
  bool _stayLoggedIn = true;

  @override
  void initState() {
    super.initState();
    _notice = widget.initialNotice;
  }

  EmailAuthBackend? get _emailAuth {
    final service = backend;
    final auth = service is EmailAuthBackend
        ? service as EmailAuthBackend
        : null;
    return auth?.emailLinksEnabled == true ? auth : null;
  }

  Future<void> _emailAction({required bool recovery}) async {
    final service = _emailAuth;
    if (_loading || service == null) return;
    setState(() {
      _loading = true;
      _error = null;
      _notice = null;
    });
    try {
      if (recovery) {
        await service.requestPasswordReset(_email.text.trim());
      } else {
        await service.resendConfirmation(_email.text.trim());
      }
      if (mounted) {
        setState(() {
          _password.clear();
          _notice =
              'Si cette adresse est éligible, vous recevrez un courriel. Ouvrez le dernier lien sur cet appareil dans une heure au maximum.';
        });
      }
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is BackendFailure
              ? error.message
              : 'Connexion par courriel temporairement indisponible.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submit() async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      _notice = null;
    });
    try {
      if (_isSignUp) {
        final outcome = await backend.signUp(
          email: _email.text.trim(),
          password: _password.text,
          name: _name.text.trim(),
          remember: _stayLoggedIn,
        );
        if (!mounted) return;
        if (outcome == SignUpOutcome.confirmationRequired) {
          setState(() {
            _password.clear();
            _notice =
                'Confirmez votre compte par courriel, puis revenez vous connecter.';
            _isSignUp = false;
          });
          return;
        }
      } else {
        await backend.signIn(
          email: _email.text.trim(),
          password: _password.text,
          remember: _stayLoggedIn,
        );
      }
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const HomeScreen()),
      );
    } catch (e) {
      if (mounted) {
        setState(
          () => _error = e is BackendFailure
              ? e.message
              : 'Connexion impossible. Réessayez.',
        );
      }
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _name.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    body: SafeArea(
      child: Align(
        alignment: Alignment.topCenter,
        child: SizedBox(
          width: 440,
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
                    color: kAccent,
                    fontSize: 30,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.5,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Bourse de Casablanca',
                  textAlign: TextAlign.center,
                  style: GoogleFonts.inter(color: kTextMuted, fontSize: 13),
                ),
                const SizedBox(height: 24),
                Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    color: kSurface,
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(color: kBorder),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        _isSignUp ? 'Créer un compte' : 'Connexion',
                        style: GoogleFonts.inter(
                          color: kTextPrimary,
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 20),
                      if (_isSignUp) ...[
                        TextField(
                          controller: _name,
                          decoration: const InputDecoration(
                            labelText: 'Nom (facultatif)',
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      TextField(
                        controller: _email,
                        autofillHints: const [AutofillHints.email],
                        textInputAction: TextInputAction.next,
                        keyboardType: TextInputType.emailAddress,
                        decoration: const InputDecoration(labelText: 'Email'),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _password,
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Mot de passe',
                        ),
                      ),
                      const SizedBox(height: 8),
                      // Stay logged in checkbox
                      Row(
                        children: [
                          SizedBox(
                            width: 24,
                            height: 24,
                            child: Checkbox(
                              value: _stayLoggedIn,
                              activeColor: kAccent,
                              checkColor: kBg,
                              side: const BorderSide(color: kTextMuted),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(4),
                              ),
                              onChanged: (v) =>
                                  setState(() => _stayLoggedIn = v ?? true),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: GestureDetector(
                              onTap: () => setState(
                                () => _stayLoggedIn = !_stayLoggedIn,
                              ),
                              child: Text(
                                'Rester connecté',
                                style: GoogleFonts.inter(
                                  color: kTextMuted,
                                  fontSize: 13,
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (_error != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          _error!,
                          style: TextStyle(color: kNegative, fontSize: 13),
                        ),
                      ],
                      if (_notice != null) ...[
                        const SizedBox(height: 12),
                        Text(
                          _notice!,
                          style: TextStyle(color: kAccent, fontSize: 13),
                        ),
                      ],
                      const SizedBox(height: 16),
                      SizedBox(
                        height: 48,
                        child: ElevatedButton(
                          onPressed: _loading ? null : _submit,
                          child: _loading
                              ? const SizedBox(
                                  height: 20,
                                  width: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: kBg,
                                  ),
                                )
                              : Text(
                                  _isSignUp
                                      ? 'Créer un compte'
                                      : 'Se connecter',
                                ),
                        ),
                      ),
                      const SizedBox(height: 16),
                      if (!_isSignUp && _emailAuth != null) ...[
                        TextButton(
                          onPressed: _loading
                              ? null
                              : () => _emailAction(recovery: true),
                          child: const Text('Mot de passe oublié ?'),
                        ),
                        TextButton(
                          onPressed: _loading
                              ? null
                              : () => _emailAction(recovery: false),
                          child: const Text(
                            'Renvoyer le courriel de confirmation',
                          ),
                        ),
                      ],
                      // Toggle sign in / sign up
                      Wrap(
                        alignment: WrapAlignment.center,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Text(
                            _isSignUp
                                ? 'Déjà un compte ? '
                                : 'Pas encore de compte ? ',
                            style: GoogleFonts.inter(
                              color: kTextMuted,
                              fontSize: 13,
                            ),
                          ),
                          GestureDetector(
                            onTap: _loading
                                ? null
                                : () => setState(() {
                                    _isSignUp = !_isSignUp;
                                    _error = null;
                                    _notice = null;
                                  }),
                            child: Text(
                              _isSignUp ? 'Connexion' : 'Créer un compte',
                              style: GoogleFonts.inter(
                                color: kAccent,
                                fontSize: 13,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    ),
  );
}
