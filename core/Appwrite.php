<?php
require_once __DIR__ . '/backend.php';
/** Compatibility names for the migrated Supabase clients.
 * Retired network calls fail closed. Portfolio writes use record_trade instead.
 */
function aw_request(string $method, string $path, array $data = [], ?string $session = null): array
{
    throw new RuntimeException('The retired backend is unavailable. Use Supabase.');
}

function aw_get(string $path, ?string $session = null): array
{
    return aw_request('GET', $path, [], $session);
}

function aw_post(string $path, array $data, ?string $session = null): array
{
    return aw_request('POST', $path, $data, $session);
}

function aw_patch(string $path, array $data, ?string $session = null): array
{
    return aw_request('PATCH', $path, $data, $session);
}

function aw_delete(string $path, ?string $session = null): array
{
    return aw_request('DELETE', $path, [], $session);
}

/**
 * List documents from a collection.
 */
function aw_list_docs(string $collectionId, array $queries = [], ?string $session = null): array
{
    if (in_array($collectionId, ['achats', 'ventes', 'portefeuille', 'benefits'], true)) {
        return sb_app()->listDocuments($collectionId, $queries, sb_access_token());
    }
    return sb_market()->listDocuments($collectionId, $queries);
}

// ─── Query builder helpers ────────────────────────────────────────────────────

function q_equal(string $attr, $val): string {
    return json_encode(['method' => 'equal', 'attribute' => $attr, 'values' => [$val]]);
}
function q_order_desc(string $attr): string {
    return json_encode(['method' => 'orderDesc', 'attribute' => $attr]);
}
function q_order_asc(string $attr): string {
    return json_encode(['method' => 'orderAsc', 'attribute' => $attr]);
}
function q_limit(int $n): string {
    return json_encode(['method' => 'limit', 'values' => [$n]]);
}
function q_greater_than(string $attr, $val): string {
    return json_encode(['method' => 'greaterThan', 'attribute' => $attr, 'values' => [$val]]);
}
function q_greater_equal(string $attr, $val): string {
    return json_encode(['method' => 'greaterThanEqual', 'attribute' => $attr, 'values' => [$val]]);
}
function q_offset(int $n): string {
    return json_encode(['method' => 'offset', 'values' => [$n]]);
}

/**
 * Return the total document count for a collection (ignores the documents array).
 */
function aw_count_docs(string $collectionId, array $queries = [], ?string $session = null): int
{
    return sb_market()->countDocuments($collectionId, $queries);
}

/**
 * Read a named batch sequentially through the migrated Supabase adapter.
 * $requests: [ 'key' => ['collection', [queries], $session|null], ... ]
 * Returns:   [ 'key' => [documents], ... ]
 */
function aw_multi_list_docs(array $requests): array
{
    $results = [];
    foreach ($requests as $key => [$collection, $queries, $session]) {
        $results[$key] = aw_list_docs($collection, $queries, $session);
    }
    return $results;
}

/**
 * Create a document in a collection.
 */
function aw_create_doc(string $collectionId, array $data, array $permissions = [], ?string $session = null): array
{
    throw new RuntimeException('Direct document writes are retired. Use the authorized Supabase operation.');
}

/**
 * Update (patch) a document.
 */
function aw_update_doc(string $collectionId, string $docId, array $data, ?string $session = null): array
{
    throw new RuntimeException('Direct document writes are retired. Use the authorized Supabase operation.');
}

/**
 * Delete a document.
 */
function aw_delete_doc(string $collectionId, string $docId, ?string $session = null): array
{
    throw new RuntimeException('Direct document writes are retired. Use the authorized Supabase operation.');
}

/**
 * Return the current user's session secret from PHP session, or null.
 */
function aw_session(): ?string
{
    return sb_access_token();
}

/**
 * Return the current authenticated Supabase user ID, or null.
 */
function aw_user_id(): ?string
{
    return $_SESSION['USER_ID'] ?? null;
}

/**
 * Permissions array for a given userId.
 */
function aw_user_permissions(string $userId): array
{
    return [
        'read("user:' . $userId . '")',
        'write("user:' . $userId . '")',
    ];
}
