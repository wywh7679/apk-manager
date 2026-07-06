<?php
require_once __DIR__ . '/includes/bootstrap.php';
if (is_logged_in()) {
    redirect('/admin/items.php');
}
$error = '';
if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    verify_csrf();
    $username = trim($_POST['username'] ?? '');
    $password = $_POST['password'] ?? '';
    if (hash_equals(ADMIN_USERNAME, $username) && password_verify($password, ADMIN_PASSWORD_HASH)) {
        session_regenerate_id(true);
        $_SESSION['authenticated'] = true;
        flash('You are now logged in.');
        redirect('/admin/items.php');
    }
    $error = 'Invalid username or password.';
}
include __DIR__ . '/includes/header.php';
?>
<h1>Admin Login</h1>
<?php if ($error): ?><div class="error"><?= h($error) ?></div><?php endif; ?>
<form method="post" class="panel form-narrow">
    <input type="hidden" name="csrf_token" value="<?= h(csrf_token()) ?>">
    <label>Username <input type="text" name="username" required autofocus></label>
    <label>Password <input type="password" name="password" required></label>
    <button type="submit">Log in</button>
</form>
<p class="help">Set <code>APK_MANAGER_ADMIN_USER</code> and <code>APK_MANAGER_ADMIN_PASSWORD_HASH</code> in IIS for production.</p>
<?php include __DIR__ . '/includes/footer.php'; ?>
