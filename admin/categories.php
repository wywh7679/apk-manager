<?php
require_once __DIR__ . '/../includes/bootstrap.php';
require_login();
$categories = categories_all();
$editId = $_GET['edit'] ?? '';
$editing = $editId ? find_by_id($categories, $editId) : null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    verify_csrf();
    $action = $_POST['action'] ?? '';
    $categories = read_json_file(CATEGORIES_FILE);

    if ($action === 'save') {
        $id = $_POST['id'] ?? '';
        $name = trim($_POST['name'] ?? '');
        if ($name === '') {
            flash('Category name is required.');
            redirect('/admin/categories.php');
        }
        if ($id !== '') {
            foreach ($categories as &$category) {
                if (($category['id'] ?? '') === $id) {
                    $category['name'] = $name;
                    break;
                }
            }
            unset($category);
            flash('Category updated.');
        } else {
            $categories[] = ['id' => slug_id('cat'), 'name' => $name];
            flash('Category added.');
        }
        write_json_file(CATEGORIES_FILE, $categories);
    } elseif ($action === 'delete') {
        $id = $_POST['id'] ?? '';
        $categories = array_values(array_filter($categories, static function ($category) use ($id) {
            return ($category['id'] ?? '') !== $id;
        }));
        $items = read_json_file(ITEMS_FILE);
        foreach ($items as &$item) {
            $item['categories'] = array_values(array_filter($item['categories'] ?? [], static function ($categoryId) use ($id) {
                return $categoryId !== $id;
            }));
        }
        unset($item);
        write_json_file(ITEMS_FILE, $items);
        write_json_file(CATEGORIES_FILE, $categories);
        flash('Category deleted.');
    }
    redirect('/admin/categories.php');
}
include __DIR__ . '/../includes/header.php';
?>
<h1>Manage Categories</h1>
<section class="panel">
    <h2><?= $editing ? 'Edit Category' : 'Add Category' ?></h2>
    <form method="post">
        <input type="hidden" name="csrf_token" value="<?= h(csrf_token()) ?>">
        <input type="hidden" name="action" value="save">
        <input type="hidden" name="id" value="<?= h($editing['id'] ?? '') ?>">
        <label>Name <input type="text" name="name" value="<?= h($editing['name'] ?? '') ?>" required></label>
        <button type="submit">Save category</button>
        <?php if ($editing): ?><a class="button secondary" href="/admin/categories.php">Cancel</a><?php endif; ?>
    </form>
</section>
<section class="panel">
    <h2>Existing Categories</h2>
    <table>
        <thead><tr><th>Name</th><th>Actions</th></tr></thead>
        <tbody>
        <?php foreach (categories_all() as $category): ?>
            <tr>
                <td><?= h($category['name']) ?></td>
                <td class="actions">
                    <a class="button secondary" href="/admin/categories.php?edit=<?= h($category['id']) ?>">Edit</a>
                    <form method="post" onsubmit="return confirm('Delete this category?');">
                        <input type="hidden" name="csrf_token" value="<?= h(csrf_token()) ?>">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="id" value="<?= h($category['id']) ?>">
                        <button type="submit" class="danger">Delete</button>
                    </form>
                </td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
</section>
<?php include __DIR__ . '/../includes/footer.php'; ?>
