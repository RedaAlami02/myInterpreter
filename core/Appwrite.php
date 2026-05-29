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
 * $session: the Appwrite cookie string stored in $_SESSION['aw_cookie']
 * @return array{body: array, status: int, cookies: string}
 */
function aw_request(string $method, string $path, array $data = [], ?string $session = null): array
{
    $url = APPWRITE_ENDPOINT . $path;

    $headers = [
        'Content-Type: application/json',
        'X-Appwrite-Project: ' . APPWRITE_PROJECT_ID,
    ];
    // Client-auth paths must NOT carry the API key — they run as anonymous guest.
    $isClientAuth = str_starts_with($path, '/account/sessions') || $path === '/account';
    if ($session !== null && $session !== '') {
        $headers[] = 'Cookie: ' . $session;
    } elseif (!$isClientAuth && defined('APPWRITE_API_KEY') && APPWRITE_API_KEY !== '') {
        $headers[] = 'X-Appwrite-Key: ' . APPWRITE_API_KEY;
    }

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HEADER         => true,
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

    $response = curl_exec($ch);
    if ($response === false) {
        $curlError = curl_error($ch);
        curl_close($ch);
        throw new RuntimeException('Appwrite request failed (curl): ' . $curlError);
    }
    $headerSize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
    $status     = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    $rawHeaders = substr($response, 0, $headerSize);
    $body       = substr($response, $headerSize);
    $decoded    = json_decode($body ?: '{}', true) ?? [];

    preg_match_all('/^Set-Cookie:\s*([^;\r\n]+)/mi', $rawHeaders, $matches);
    $cookieString = implode('; ', $matches[1] ?? []);

    return ['body' => $decoded, 'status' => $status, 'cookies' => $cookieString];
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
    $params = [];
    foreach ($queries as $q) {
        $params[] = 'queries[]=' . urlencode($q);
    }
    $qs   = $params ? '?' . implode('&', $params) : '';
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents' . $qs;
    $res  = aw_get($path, $session);
    return $res['body']['documents'] ?? [];
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
    $params = [];
    foreach (array_merge($queries, [q_limit(1)]) as $q) {
        $params[] = 'queries[]=' . urlencode($q);
    }
    $qs   = $params ? '?' . implode('&', $params) : '';
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents' . $qs;
    $res  = aw_get($path, $session);
    return (int)($res['body']['total'] ?? 0);
}

/**
 * Fire multiple aw_list_docs calls in parallel using curl_multi.
 * $requests: [ 'key' => ['collection', [queries], $session|null], ... ]
 * Returns:   [ 'key' => [documents], ... ]
 */
function aw_multi_list_docs(array $requests): array
{
    if (!function_exists('curl_multi_init')) {
        $results = [];
        foreach ($requests as $key => [$collection, $queries, $session]) {
            $results[$key] = aw_list_docs($collection, $queries, $session);
        }
        return $results;
    }

    $mh      = curl_multi_init();
    $handles = [];

    foreach ($requests as $key => [$collection, $queries, $session]) {
        $params = [];
        foreach ($queries as $q) {
            $params[] = 'queries[]=' . urlencode($q);
        }
        $qs  = $params ? '?' . implode('&', $params) : '';
        $url = APPWRITE_ENDPOINT . '/databases/' . APPWRITE_DB_ID . '/collections/' . $collection . '/documents' . $qs;

        $headers = [
            'Content-Type: application/json',
            'X-Appwrite-Project: ' . APPWRITE_PROJECT_ID,
        ];
        if ($session !== null && $session !== '') {
            $headers[] = 'Cookie: ' . $session;
        } elseif (defined('APPWRITE_API_KEY') && APPWRITE_API_KEY !== '') {
            $headers[] = 'X-Appwrite-Key: ' . APPWRITE_API_KEY;
        }

        $ch = curl_init();
        curl_setopt_array($ch, [
            CURLOPT_URL            => $url,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_HEADER         => false,
            CURLOPT_TIMEOUT        => 15,
            CURLOPT_CONNECTTIMEOUT => 8,
            CURLOPT_HTTPHEADER     => $headers,
            CURLOPT_SSL_VERIFYPEER => true,
        ]);
        curl_multi_add_handle($mh, $ch);
        $handles[$key] = $ch;
    }

    do {
        $status = curl_multi_exec($mh, $active);
        if ($active) curl_multi_select($mh);
    } while ($active > 0 && $status === CURLM_OK);

    $results = [];
    foreach ($handles as $key => $ch) {
        $errno = curl_errno($ch);
        if ($errno) {
            $err = curl_error($ch);
            curl_multi_remove_handle($mh, $ch);
            curl_close($ch);
            curl_multi_close($mh);
            throw new RuntimeException("aw_multi_list_docs curl error on '{$key}': {$err}");
        }
        $body          = curl_multi_getcontent($ch);
        $decoded       = json_decode($body ?: '{}', true) ?? [];
        $results[$key] = $decoded['documents'] ?? [];
        curl_multi_remove_handle($mh, $ch);
        curl_close($ch);
    }
    curl_multi_close($mh);

    return $results;
}

/**
 * Create a document in a collection.
 */
function aw_create_doc(string $collectionId, array $data, array $permissions = [], ?string $session = null): array
{
    $payload = ['documentId' => 'unique()', 'data' => $data];
    if ($permissions) {
        $payload['permissions'] = $permissions;
    }
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents';
    $res  = aw_post($path, $payload, $session);
    if ($res['status'] >= 400) {
        $msg = $res['body']['message'] ?? ('HTTP ' . $res['status']);
        throw new RuntimeException("aw_create_doc({$collectionId}): {$msg}");
    }
    return $res;
}

/**
 * Update (patch) a document.
 */
function aw_update_doc(string $collectionId, string $docId, array $data, ?string $session = null): array
{
    $path = '/databases/' . APPWRITE_DB_ID . '/collections/' . $collectionId . '/documents/' . $docId;
    $res  = aw_patch($path, ['data' => $data], $session);
    if ($res['status'] >= 400) {
        $msg = $res['body']['message'] ?? ('HTTP ' . $res['status']);
        throw new RuntimeException("aw_update_doc({$collectionId}/{$docId}): {$msg}");
    }
    return $res;
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
    $c = $_SESSION['aw_cookie'] ?? null;
    return ($c && $c !== '') ? $c : null;
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
