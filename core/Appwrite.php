<?php
/**
 * Appwrite REST API helper — no Composer required.
 * All requests go to APPWRITE_ENDPOINT with APPWRITE_PROJECT_ID.
 * Pass $session (the session secret from login) for user-scoped calls.
 */

define('APPWRITE_ENDPOINT',   'https://fra.cloud.appwrite.io/v1');
define('APPWRITE_PROJECT_ID', '6a12447800077d5113ae');
define('APPWRITE_DB_ID',      'myinterpreter');

/**
 * Core curl request.
 * @return array{body: array, status: int}
 */
function aw_request(string $method, string $path, array $data = [], ?string $session = null): array
{
    $url = APPWRITE_ENDPOINT . $path;

    $headers = [
        'Content-Type: application/json',
        'X-Appwrite-Project: ' . APPWRITE_PROJECT_ID,
    ];
    if ($session !== null) {
        $headers[] = 'X-Appwrite-Session: ' . $session;
    }

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 15,
        CURLOPT_CONNECTTIMEOUT => 8,
        CURLOPT_HTTPHEADER     => $headers,
        CURLOPT_SSL_VERIFYPEER => true,
    ]);

    if ($method === 'POST') {
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    } elseif ($method === 'PATCH') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'PATCH');
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    } elseif ($method === 'DELETE') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'DELETE');
    }

    $body   = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $decoded = json_decode($body ?: '{}', true) ?? [];
    return ['body' => $decoded, 'status' => $status];
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
 * $queries: use the q_*() helper functions below, e.g. [q_order_desc('date'), q_limit(500)]
 */
function aw_list_docs(string $collectionId, array $queries = [], ?string $session = null): array
{
    $params = [];
    foreach ($queries as $q) {
        $params[] = 'queries[]=' . urlencode($q);
    }
    $qs   = $params ? '?' . implode('&', $params) : '';
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents' . $qs;
    $res  = aw_get($path, $session);
    return $res['body']['documents'] ?? [];
}

// ─── Query builder helpers ─────────────────────────────────────────────────────
// Appwrite Cloud REST API uses JSON-encoded query objects.

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

/**
 * Create a document in a collection.
 * $permissions: optional array, e.g. ['read("user:uid")', 'write("user:uid")']
 */
function aw_create_doc(string $collectionId, array $data, array $permissions = [], ?string $session = null): array
{
    $payload = ['documentId' => 'unique()', 'data' => $data];
    if ($permissions) {
        $payload['permissions'] = $permissions;
    }
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents';
    return aw_post($path, $payload, $session);
}

/**
 * Update (patch) a document.
 */
function aw_update_doc(string $collectionId, string $docId, array $data, ?string $session = null): array
{
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents/' . $docId;
    return aw_patch($path, ['data' => $data], $session);
}

/**
 * Delete a document.
 */
function aw_delete_doc(string $collectionId, string $docId, ?string $session = null): array
{
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents/' . $docId;
    return aw_delete($path, $session);
}

/**
 * Return the current user's session secret from PHP session, or null.
 */
function aw_session(): ?string
{
    return $_SESSION['aw_secret'] ?? null;
}

/**
 * Return the current user's Appwrite userId, or null.
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
