<?php
// Copy this file or edit these values before publishing the site.
// Environment variables take precedence when set in IIS/FastCGI.
define('APP_NAME', getenv('APK_MANAGER_APP_NAME') ?: 'APK Manager');
define('ADMIN_USERNAME', getenv('APK_MANAGER_ADMIN_USER') ?: 'admin');
// Default password is intended only for first local setup. Change it before going live.
define('ADMIN_PASSWORD_HASH', getenv('APK_MANAGER_ADMIN_PASSWORD_HASH') ?: password_hash('change-me', PASSWORD_DEFAULT));
define('DATA_DIR', dirname(__DIR__) . DIRECTORY_SEPARATOR . 'data');
define('CATEGORIES_FILE', DATA_DIR . DIRECTORY_SEPARATOR . 'categories.json');
define('ITEMS_FILE', DATA_DIR . DIRECTORY_SEPARATOR . 'items.json');
