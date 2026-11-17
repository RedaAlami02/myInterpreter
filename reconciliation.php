<?php
require_once __DIR__ . '/core/session.php';
app_session_start();
require_once __DIR__ . '/core/i18n.php';
require_once 'config/config.php';
require_once 'core/auth.php';
require_once 'core/SupabaseApp.php';
requireLogin();

$message = null;
$error = null;
$adminDenied = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    try {
        csrf_verify();
        $action = $_POST['action'] ?? '';
        $sha = $_POST['report_sha256'] ?? '';
        $symbols = array_values(array_filter(
            array_map(static fn($s) => is_string($s) ? trim($s) : '', (array)($_POST['symbols'] ?? [])),
            static fn($s) => $s !== ''
        ));
        if (!is_string($sha) || !preg_match('/^[a-f0-9]{64}$/', $sha) || $symbols === []) {
            throw new InvalidArgumentException('Select at least one company.');
        }
        $admin = sb_admin();
        $token = sb_access_token();
        if ($action === 'approve') {
            $result = $admin->applyExchangeAnnualCandidates($token, $sha, $symbols);
            $message = 'Applied ' . (int)($result['applied'] ?? 0) . ' candidate(s); '
                . (int)($result['skipped'] ?? 0) . ' skipped.';
            $failed = [];
            foreach ((array)($result['results'] ?? []) as $entry) {
                if (($entry['status'] ?? '') === 'FAILED') {
                    $failed[] = (string)($entry['symbol'] ?? '?')
                        . ' (' . (string)($entry['reason'] ?? 'failed') . ')';
                }
            }
            if ($failed) {
                $error = 'Not applied: ' . implode(', ', $failed);
            }
        } elseif ($action === 'reject') {
            $result = $admin->rejectExchangeAnnualCandidates($token, $sha, $symbols);
            $message = 'Rejected ' . (int)($result['rejected'] ?? 0) . ' candidate(s).';
        } else {
            throw new InvalidArgumentException('Unknown action.');
        }
    } catch (SupabaseRequestException $failure) {
        if (in_array($failure->httpStatus, [401, 403], true)) {
            $adminDenied = true;
            $error = 'Administrator access required. Add this account to market_admin.admins.';
        } else {
            $error = 'The review action was not applied. Check the selected companies and try again.';
        }
    } catch (Throwable $failure) {
        $error = 'The review action was not applied. Check the selected companies and try again.';
    }
}

$candidates = [];
try {
    $candidates = sb_admin()->readExchangeAnnualCandidates(sb_access_token());
} catch (SupabaseRequestException $failure) {
    if (in_array($failure->httpStatus, [401, 403], true)) {
        $adminDenied = true;
        $error = $error ?? 'Administrator access required. Add this account to market_admin.admins.';
    } else {
        $error = $error ?? 'Pending annual candidates are unavailable. Check the reconciliation migration.';
    }
} catch (Throwable $failure) {
    $error = $error ?? 'Pending annual candidates are unavailable. Check the reconciliation migration.';
}
$groups = [];
foreach ($candidates as $candidate) {
    if (!is_array($candidate)) continue;
    $groups[(string)$candidate['report_sha256']][] = $candidate;
}
?>
<!DOCTYPE html>
<html lang="<?= ui_locale() ?>" dir="<?= ui_direction() ?>">
<head>
  <meta charset="UTF-8">
  <link rel="icon" type="image/svg+xml" href="favicon.svg">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title><?= te('myInterpreter | Annual review') ?></title>
  <link href="assets/vendor/bootstrap/bootstrap.min.css" rel="stylesheet">
  <link href="assets/css/global.css?v=5" rel="stylesheet">
  <link href="assets/css/update.css?v=3" rel="stylesheet">
  <?php require 'core/theme.php'; ?>
</head>
<body class="workspace workspace-update">
<div class="ambient" aria-hidden="true"><div class="halo halo-1"></div><div class="halo halo-2"></div><div class="halo halo-3"></div></div>
<div class="app">
  <?php include 'core/sidebar.php'; ?>
  <main class="main">
    <div class="update-wrap animate-up">
      <?php if ($message): ?><div class="alert alert-success"><?= htmlspecialchars($message) ?></div><?php endif; ?>
      <?php if ($error): ?><div class="alert alert-danger"><?= htmlspecialchars($error) ?></div><?php endif; ?>

      <h2 class="mb-1" style="font-family:var(--font-display);font-weight:700;font-size:1.5rem;">
        Exchange annual review
      </h2>
      <p class="muted" style="font-size:0.85rem;">
        Consolidated and standalone companies with a current exchange annual row, including
        banks, insurers and standalone-account issuers. These are exchange proposals, not
        primary-document verification. Approve only after checking the fields and the source
        evidence. Access is checked by the database against <code>market_admin.admins</code>.
      </p>
      <p class="muted" style="font-size:0.78rem;">
        <strong>cp</strong> equity, MAD · <strong>bpa</strong> earnings per share, MAD ·
        <strong>roe</strong> percent · <strong>revenue</strong> and
        <strong>net_profit</strong> millions MAD · <strong>profit_margin</strong> percent.
        Approval writes annual fields only and recomputes BPA from the current share count.
      </p>

      <?php if ($adminDenied): ?>
        <div class="alert alert-warning">
          This account is signed in but is not in <code>market_admin.admins</code>, so the
          annual review data is hidden. Add the account in Supabase before retrying.
        </div>
      <?php endif; ?>

      <?php if (!$groups): ?>
        <div class="alert alert-info">No pending candidates. The monthly cloud job stages them here.</div>
      <?php endif; ?>

      <?php foreach ($groups as $sha => $rows): ?>
        <form method="POST" class="mb-4" style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px">
          <?= csrf_field() ?>
          <input type="hidden" name="report_sha256" value="<?= htmlspecialchars($sha) ?>">
          <div class="d-flex justify-content-between align-items-center mb-2" style="gap:12px;flex-wrap:wrap">
            <div>
              <strong>Report <?= htmlspecialchars(substr($sha, 0, 12)) ?>…</strong>
              <div class="muted" style="font-size:0.75rem;">
                Generated <?= htmlspecialchars((string)($rows[0]['report_generated_at'] ?? '')) ?>
              </div>
            </div>
            <div>
              <button class="btn btn-success btn-sm" name="action" value="approve">Approve selected</button>
              <button class="btn btn-outline-danger btn-sm" name="action" value="reject">Reject selected</button>
            </div>
          </div>
          <div style="overflow-x:auto">
            <table class="table table-sm align-middle" style="font-size:0.82rem">
              <thead>
                <tr>
                  <th><input type="checkbox" class="js-select-all" aria-label="Select all"></th><th>Symbol</th><th>Company</th><th>FY</th><th>Class</th>
                  <th>Fields</th><th>Warnings</th><th>Evidence</th>
                </tr>
              </thead>
              <tbody>
              <?php foreach ($rows as $row): ?>
                <?php
                  $fields = is_array($row['fields'] ?? null)
                      ? $row['fields']
                      : json_decode((string)($row['fields'] ?? '{}'), true);
                  $warnings = is_array($row['warnings'] ?? null)
                      ? $row['warnings']
                      : json_decode((string)($row['warnings'] ?? '[]'), true);
                  $fieldText = [];
                  foreach ((array)$fields as $key => $value) {
                      $fieldText[] = $key . '=' . (is_scalar($value) ? (string)$value : json_encode($value));
                  }
                ?>
                <tr>
                  <td><input type="checkbox" name="symbols[]" value="<?= htmlspecialchars((string)$row['symbol']) ?>"></td>
                  <td><strong><?= htmlspecialchars((string)$row['symbol']) ?></strong></td>
                  <td><?= htmlspecialchars((string)$row['company_name']) ?></td>
                  <td><?= (int)$row['fiscal_year'] ?></td>
                  <td><?= htmlspecialchars((string)($row['review_class'] ?? '')) ?></td>
                  <td style="max-width:420px"><?= htmlspecialchars(implode(' · ', $fieldText)) ?></td>
                  <td><?= htmlspecialchars(implode(' · ', array_map('strval', (array)$warnings))) ?></td>
                  <td title="<?= htmlspecialchars((string)$row['page_sha256']) ?>"><?= htmlspecialchars(substr((string)$row['page_sha256'], 0, 10)) ?>…</td>
                </tr>
              <?php endforeach; ?>
              </tbody>
            </table>
          </div>
        </form>
      <?php endforeach; ?>
    </div>
  </main>
</div>
<script>
document.querySelectorAll('.js-select-all').forEach(function (box) {
  box.addEventListener('change', function () {
    box.closest('form').querySelectorAll('input[name="symbols[]"]').forEach(function (item) {
      item.checked = box.checked;
    });
  });
});
</script>
</body>
</html>
