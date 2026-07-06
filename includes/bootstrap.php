<?php
require_once __DIR__ . '/config.php';

if (session_status() === PHP_SESSION_NONE) {
    session_start();
}

function ensure_data_files(): void
{
    if (!is_dir(DATA_DIR)) {
        mkdir(DATA_DIR, 0755, true);
    }

    foreach ([CATEGORIES_FILE, ITEMS_FILE] as $file) {
        if (!file_exists($file)) {
            file_put_contents($file, json_encode([], JSON_PRETTY_PRINT));
        }
    }
}

function read_json_file(string $file): array
{
    ensure_data_files();
    $json = file_get_contents($file);
    if ($json === false || trim($json) === '') {
        return [];
    }

    $data = json_decode($json, true);
    return is_array($data) ? $data : [];
}

function write_json_file(string $file, array $data): bool
{
    ensure_data_files();
    $tmp = $file . '.tmp';
    $json = json_encode(array_values($data), JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    if ($json === false || file_put_contents($tmp, $json, LOCK_EX) === false) {
        return false;
    }

    return rename($tmp, $file);
}

function categories_all(): array
{
    $categories = read_json_file(CATEGORIES_FILE);
    usort($categories, static function ($a, $b) {
        return strcasecmp($a['name'] ?? '', $b['name'] ?? '');
    });
    return $categories;
}

function items_all(): array
{
    $items = read_json_file(ITEMS_FILE);
    usort($items, static function ($a, $b) {
        $order = (int)($a['sort_order'] ?? 0) <=> (int)($b['sort_order'] ?? 0);
        return $order !== 0 ? $order : strcasecmp($a['title'] ?? '', $b['title'] ?? '');
    });
    return $items;
}

function find_by_id(array $records, string $id): ?array
{
    foreach ($records as $record) {
        if (($record['id'] ?? '') === $id) {
            return $record;
        }
    }
    return null;
}

function slug_id(string $prefix): string
{
    return $prefix . '_' . bin2hex(random_bytes(8));
}

function h(?string $value): string
{
    return htmlspecialchars((string)$value, ENT_QUOTES, 'UTF-8');
}

function is_logged_in(): bool
{
    return !empty($_SESSION['authenticated']);
}

function require_login(): void
{
    if (!is_logged_in()) {
        header('Location: /login.php');
        exit;
    }
}

function csrf_token(): string
{
    if (empty($_SESSION['csrf_token'])) {
        $_SESSION['csrf_token'] = bin2hex(random_bytes(32));
    }
    return $_SESSION['csrf_token'];
}

function verify_csrf(): void
{
    $token = $_POST['csrf_token'] ?? '';
    if (!hash_equals($_SESSION['csrf_token'] ?? '', $token)) {
        http_response_code(400);
        exit('Invalid CSRF token.');
    }
}

function redirect(string $path): void
{
    header('Location: ' . $path);
    exit;
}

function flash(?string $message = null): ?string
{
    if ($message !== null) {
        $_SESSION['flash'] = $message;
        return null;
    }
    $current = $_SESSION['flash'] ?? null;
    unset($_SESSION['flash']);
    return $current;
}
