<?php
declare(strict_types=1);

// Place this file in the same web directory as the APK files it should publish.
// Set the same token in apk_manager_config.json on the Windows client.
const APK_MANAGER_TOKEN = 'change-this-token-before-deploying';

function request_token(): string
{
    $headers = function_exists('getallheaders') ? getallheaders() : [];
    foreach ($headers as $name => $value) {
        if (strcasecmp((string) $name, 'X-APK-Manager-Token') === 0) {
            return trim((string) $value);
        }
        if (strcasecmp((string) $name, 'Authorization') === 0) {
            $value = trim((string) $value);
            if (stripos($value, 'Bearer ') === 0) {
                return trim(substr($value, 7));
            }
        }
    }

    return '';
}

function respond(int $status, array $payload): void
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

if (APK_MANAGER_TOKEN === 'change-this-token-before-deploying') {
    respond(500, ['error' => 'Server token must be changed before deployment.']);
}

if (!hash_equals(APK_MANAGER_TOKEN, request_token())) {
    respond(401, ['error' => 'Unauthorized']);
}

$script = basename(__FILE__);
$baseUrl = rtrim(dirname($_SERVER['SCRIPT_NAME'] ?? ''), '/\\');
$scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
$host = $_SERVER['HTTP_HOST'] ?? 'localhost';
$scriptHref = $scheme . '://' . $host . ($baseUrl === '' ? '' : $baseUrl) . '/' . rawurlencode($script);

if (isset($_GET['download'])) {
    $requested = basename((string) $_GET['download']);
    $path = __DIR__ . DIRECTORY_SEPARATOR . $requested;

    if ($requested === '' || strtolower(pathinfo($requested, PATHINFO_EXTENSION)) !== 'apk' || !is_file($path)) {
        respond(404, ['error' => 'APK not found']);
    }

    header('Content-Type: application/vnd.android.package-archive');
    header('Content-Length: ' . filesize($path));
    header('Content-Disposition: attachment; filename="' . addcslashes($requested, '\"') . '"');
    header('Cache-Control: private, no-store');
    readfile($path);
    exit;
}

$apks = [];

foreach (new DirectoryIterator(__DIR__) as $file) {
    if (!$file->isFile()) {
        continue;
    }

    $filename = $file->getFilename();
    if ($filename === $script || strtolower($file->getExtension()) !== 'apk') {
        continue;
    }

    $apks[] = [
        'name' => $filename,
        'url' => $scriptHref . '?download=' . rawurlencode($filename),
        'size' => $file->getSize(),
        'modified' => gmdate(DATE_ATOM, $file->getMTime()),
    ];
}

usort($apks, static fn (array $a, array $b): int => strcasecmp($a['name'], $b['name']));

respond(200, ['apks' => $apks]);
