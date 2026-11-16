<?php
// No backend or real accounts involved.
$mode = $argv[1] ?? 'ar';
$_SESSION = [];
$_GET = [];
$_COOKIE = [];
if ($mode === 'cookie') $_COOKIE['mi_locale'] = 'ary';
elseif ($mode === 'invalid') $_GET['lang'] = ['../../config'];
else $_GET['lang'] = $mode;
require __DIR__ . '/../core/i18n.php';
function check($value, string $message): void {
    if (!$value) throw new RuntimeException($message);
}
$expected = $mode === 'cookie' ? 'ary' : ($mode === 'invalid' ? 'fr' : $mode);
check(ui_locale() === $expected, 'Allowlisted language selection');
check(ui_direction() === (in_array($expected, ['ar', 'ary'], true) ? 'rtl' : 'ltr'), 'Direction');
if ($expected !== 'fr') {
    check(t('Portefeuille') !== 'Portefeuille', 'Portfolio translated');
    check(t('Bénéfice net') !== 'Bénéfice net', 'Shared financial terminology');
    check(str_contains(te('Achat de {quantity} × {name} enregistré.', ['quantity' => 12, 'name' => '<script>']), '&lt;script&gt;'), 'Placeholder escaped');
}
check(t('DEMO Holdings') === 'DEMO Holdings', 'Company names unchanged');
check(te('<script>') === '&lt;script&gt;', 'Fallback escaped');
check(t('Historique &amp; ratios') === t('Historique & ratios'), 'Entity normalization');
$ar = json_decode(file_get_contents(__DIR__ . '/../locales/ar.json'), true, 512, JSON_THROW_ON_ERROR);
$ary = json_decode(file_get_contents(__DIR__ . '/../locales/ary.json'), true, 512, JSON_THROW_ON_ERROR);
$en = json_decode(file_get_contents(__DIR__ . '/../locales/en.json'), true, 512, JSON_THROW_ON_ERROR);
check(!array_diff_key($ar, $en) && !array_diff_key($en, $ar), 'English catalog covers the same messages');
foreach ($en as $key => $value) {
    check(is_string($value) && trim($value) !== '', 'English catalog entry: ' . $key);
    preg_match_all('/\{\w+\}/', $key, $base);
    preg_match_all('/\{\w+\}/', $value, $translated);
    sort($base[0]); sort($translated[0]);
    check($base[0] === $translated[0], 'English placeholders: ' . $key);
}
foreach ($ary as $key => $value) {
    check(isset($ar[$key]), 'Darija override has Arabic base: ' . $key);
    preg_match_all('/\{\w+\}/', $key, $base);
    preg_match_all('/\{\w+\}/', $value, $translated);
    sort($base[0]); sort($translated[0]);
    check($base[0] === $translated[0], 'Darija placeholders: ' . $key);
}
foreach ($ar as $key => $value) {
    check(is_string($value) && preg_match('/\p{Arabic}/u', $value), 'Arabic catalog entry: ' . $key);
    preg_match_all('/\{\w+\}/', $key, $base);
    preg_match_all('/\{\w+\}/', $value, $translated);
    sort($base[0]); sort($translated[0]);
    check($base[0] === $translated[0], 'Arabic placeholders: ' . $key);
}
echo "PASS i18n $mode: locale, fallback, escaping, catalogs, placeholders\n";
