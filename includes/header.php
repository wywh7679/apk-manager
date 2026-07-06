<?php require_once __DIR__ . '/bootstrap.php'; ?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title><?= h(APP_NAME) ?></title>
    <link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="site-header">
    <a class="brand" href="/index.php"><?= h(APP_NAME) ?></a>
    <nav>
        <a href="/index.php">Directory</a>
        <?php if (is_logged_in()): ?>
            <a href="/admin/items.php">Manage Items</a>
            <a href="/admin/categories.php">Manage Categories</a>
            <a href="/logout.php">Log out</a>
        <?php else: ?>
            <a href="/login.php">Admin log in</a>
        <?php endif; ?>
    </nav>
</header>
<main class="container">
<?php if ($message = flash()): ?>
    <div class="flash"><?= h($message) ?></div>
<?php endif; ?>
