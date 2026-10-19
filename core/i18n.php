<?php
// Local catalogs only: no account data is sent to translation services.
function ui_locale(): string {
    static $locale;
    if ($locale !== null) return $locale;
    $candidate = $_GET['lang'] ?? $_SESSION['ui_locale'] ?? $_COOKIE['mi_locale'] ?? 'fr';
    $locale = is_string($candidate) && in_array($candidate, ['fr', 'en', 'ar', 'ary'], true) ? $candidate : 'fr';
    if (isset($_GET['lang']) && is_string($_GET['lang']) && in_array($_GET['lang'], ['fr', 'en', 'ar', 'ary'], true)) {
        $_SESSION['ui_locale'] = $locale;
        if (PHP_SAPI !== 'cli' && !headers_sent()) {
            setcookie('mi_locale', $locale, ['expires' => time() + 31536000, 'path' => '/',
                'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
                'httponly' => true, 'samesite' => 'Lax']);
        }
    }
    return $locale;
}
function ui_key(string $text): string {
    return preg_replace('/\s+/u', ' ', trim(html_entity_decode($text, ENT_QUOTES | ENT_HTML5, 'UTF-8')));
}
function ui_messages(): array {
    static $messages;
    if ($messages !== null) return $messages;
    $messages = [];
    if (ui_locale() === 'fr') return $messages;
    $files = [ui_locale() === 'en' ? 'en' : 'ar'];
    if (ui_locale() === 'ary') $files[] = 'ary';
    foreach ($files as $file) {
        $catalog = json_decode(file_get_contents(__DIR__ . '/../locales/' . $file . '.json'), true, 512, JSON_THROW_ON_ERROR);
        foreach ($catalog as $key => $value) $messages[ui_key($key)] = $value;
    }
    return $messages;
}
function t(string $text, array $values = []): string {
    $key = ui_key($text);
    $translated = ui_messages()[$key] ?? html_entity_decode($text, ENT_QUOTES | ENT_HTML5, 'UTF-8');
    foreach ($values as $name => $value) $translated = str_replace('{' . $name . '}', (string)$value, $translated);
    return $translated;
}
function te(string $text, array $values = []): string {
    return htmlspecialchars(t($text, $values), ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}
function ui_direction(): string { return in_array(ui_locale(), ['ar', 'ary'], true) ? 'rtl' : 'ltr'; }
ui_locale();
