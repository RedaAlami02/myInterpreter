<?php // Theme boot runs before the body to avoid flashing the opposite palette. ?>
<?php require_once __DIR__ . '/i18n.php'; ?>
<script id="ui-locale" type="application/json"><?= json_encode(['locale' => ui_locale(), 'messages' => ui_messages()], JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_UNESCAPED_UNICODE) ?></script>
<script src="assets/js/i18n.js?v=1"></script>
<script src="assets/js/theme.js?v=3"></script>
<script src="assets/js/workspace-charts.js?v=2"></script>
<link rel="stylesheet" href="assets/css/workspace.css?v=3">
<link rel="stylesheet" href="assets/css/rtl.css?v=1">
