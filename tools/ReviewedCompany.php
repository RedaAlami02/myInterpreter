<?php
require_once __DIR__ . '/../core/Appwrite.php';

/**
 * Applies one reviewed company disclosure through the owner RPC.
 * Reads use the signed-in token; writes are rechecked by the database.
 */
final class ReviewedCompany
{
    public function __construct(
        private SupabaseMarketReader $reader,
        private SupabaseAdminClient $admin,
        private string $accessToken
    ) {
    }

    /** @return array{symbol:string,name:string,changes:string[],applied:bool,backup:?string} */
    public function apply(array $review, string $symbol, bool $apply): array
    {
        $name = $review['name'] ?? null;
        $fields = $review['fields'] ?? null;
        if (!is_string($name) || $name === '' || !is_array($fields) || $fields === []) {
            throw new InvalidArgumentException('Invalid reviewed disclosure.');
        }
        $rows = $this->reader->listDocuments('company', [q_equal('name', $name), q_limit(2)]);
        if (count($rows) !== 1) {
            throw new RuntimeException('Expected exactly one company');
        }
        $current = $rows[0];
        $incomingYear = (int)($fields['fiscal_year'] ?? 0);
        if ((int)($current['fiscal_year'] ?? 0) > $incomingYear) {
            throw new RuntimeException('Refusing to overwrite newer accounts');
        }
        $changes = [];
        foreach ($fields as $key => $value) {
            if (!$this->same($current[$key] ?? null, $value)) {
                $changes[$key] = $value;
            }
        }
        $summary = [
            'symbol' => $symbol,
            'name' => $name,
            'changes' => array_keys($changes),
            'applied' => false,
            'backup' => null,
        ];
        if (!$apply || !$changes) return $summary;
        $summary['backup'] = $this->backup($current);
        $receipt = $this->admin->updateCompany($this->accessToken, $name, $changes);
        if ($receipt['status'] !== 'UPDATED') {
            throw new RuntimeException('Company update was not applied');
        }
        $saved = $this->reader->listDocuments('company', [q_equal('name', $name), q_limit(1)]);
        $row = $saved[0] ?? [];
        foreach ($changes as $key => $value) {
            if (!$this->same($row[$key] ?? null, $value)) {
                throw new RuntimeException('Read-back mismatch: ' . $key);
            }
        }
        $summary['applied'] = true;
        return $summary;
    }

    /** A redundant write must not be triggered by int/float representation. */
    private function same($stored, $reviewed): bool
    {
        if ($stored === null || $reviewed === null) return $stored === $reviewed;
        if (is_bool($stored) || is_bool($reviewed)) return $stored === $reviewed;
        if (is_numeric($stored) && is_numeric($reviewed)) {
            return abs((float)$stored - (float)$reviewed) < 1e-9;
        }
        return $stored === $reviewed;
    }

    private function backup(array $current): string
    {
        $path = tempnam(sys_get_temp_dir(), 'myinterpreter-company-');
        if ($path === false
            || file_put_contents(
                $path,
                json_encode($current, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)
            ) === false) {
            throw new RuntimeException('Backup failed; no changes made');
        }
        chmod($path, 0600);
        return $path;
    }
}
