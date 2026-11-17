<?php
// Preview is available only on PHP's local development server.
if (PHP_SAPI !== 'cli-server' || !in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1'], true)) {
    http_response_code(404);
    exit;
}
require_once __DIR__ . '/core/i18n.php';
require_once __DIR__ . '/config/config.php';
$rows = [
    ['AFRIC INDUSTRIES', 1, 333.20, 325],
    ['ARADEI CAPITAL', 1, 437.10, 431],
    ['DELTA HOLDING', 30, 1602, 1464],
    ['IAM', 10, 920, 882],
    ['IMMORENTE INVEST', 7, 641.20, 639.80],
    ['M2M Group', 1, 401.40, 400],
    ['MUTANDIS', 8, 1911.05, 1816],
    ['PROMOPHARM', 2, 2800, 2960],
    ['SGTM', 1, 595, 580],
    ['COSUMAR', 2, 356, 350],
];
$holdings = array_map(fn($r) => ['c_name' => $r[0], 'quantity' => $r[1]], $rows);
$chartBuys = array_column($rows, 2);
$chartValues = array_column($rows, 3);
?>
<!doctype html>
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Portfolio · Local preview</title>
    <link rel="stylesheet" href="assets/vendor/bootstrap/bootstrap.min.css">
    <link rel="stylesheet" href="assets/css/global.css?v=5">
    <link rel="stylesheet" href="assets/css/portfolio.css?v=5">
    <?php require __DIR__ . '/core/theme.php'; ?>
</head>
<body class="workspace workspace-portfolio">
<main style="padding:24px">
    <h1>Portefeuille</h1>
    <p class="muted">Aperçu local · données de démonstration</p>
    <?php require __DIR__ . '/core/holdings_table.php'; ?>
</main>
<script>
function toggleCols(group, button) {
    const open = document.getElementById('holdingsTbl').classList.toggle('show-' + group);
    button.classList.toggle('active', open);
    button.setAttribute('aria-pressed', String(open));
}
document.querySelectorAll('.col-toggle').forEach(button => button.click());
</script>
</body>
</html>
