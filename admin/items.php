<?php
require_once __DIR__ . '/../includes/bootstrap.php';
require_login();
$categories = categories_all();
$items = items_all();
$editId = $_GET['edit'] ?? '';
$editing = $editId ? find_by_id($items, $editId) : null;

if ($_SERVER['REQUEST_METHOD'] === 'POST') {
    verify_csrf();
    $action = $_POST['action'] ?? '';
    $items = read_json_file(ITEMS_FILE);

    if ($action === 'save') {
        $id = $_POST['id'] ?? '';
        $title = trim($_POST['title'] ?? '');
        $description = trim($_POST['description'] ?? '');
        $link = trim($_POST['link'] ?? '');
        $sortOrder = (int)($_POST['sort_order'] ?? 0);
        $selectedCategories = array_values(array_intersect($_POST['categories'] ?? [], array_column(categories_all(), 'id')));

        if ($title === '' || $link === '' || filter_var($link, FILTER_VALIDATE_URL) === false) {
            flash('A title and valid URL are required.');
            redirect('/admin/items.php' . ($id ? '?edit=' . rawurlencode($id) : ''));
        }

        $record = [
            'id' => $id ?: slug_id('item'),
            'title' => $title,
            'description' => $description,
            'link' => $link,
            'categories' => $selectedCategories,
            'sort_order' => $sortOrder,
        ];

        if ($id !== '') {
            foreach ($items as &$item) {
                if (($item['id'] ?? '') === $id) {
                    $item = $record;
                    break;
                }
            }
            unset($item);
            flash('Item updated.');
        } else {
            $items[] = $record;
            flash('Item added.');
        }
        write_json_file(ITEMS_FILE, $items);
    } elseif ($action === 'delete') {
        $id = $_POST['id'] ?? '';
        $items = array_values(array_filter($items, static function ($item) use ($id) {
            return ($item['id'] ?? '') !== $id;
        }));
        write_json_file(ITEMS_FILE, $items);
        flash('Item deleted.');
    }
    redirect('/admin/items.php');
}
include __DIR__ . '/../includes/header.php';
?>
<h1>Manage Items</h1>
<section class="panel">
    <h2><?= $editing ? 'Edit Item' : 'Add Item' ?></h2>
    <form method="post" class="grid-form">
        <input type="hidden" name="csrf_token" value="<?= h(csrf_token()) ?>">
        <input type="hidden" name="action" value="save">
        <input type="hidden" name="id" value="<?= h($editing['id'] ?? '') ?>">
        <label>Title <input type="text" name="title" value="<?= h($editing['title'] ?? '') ?>" required></label>
        <label>Link <input type="url" name="link" value="<?= h($editing['link'] ?? '') ?>" required placeholder="https://example.com"></label>
        <label>Order <input type="number" name="sort_order" value="<?= h((string)($editing['sort_order'] ?? 0)) ?>"></label>
        <label class="full">Description <textarea name="description" rows="4"><?= h($editing['description'] ?? '') ?></textarea></label>
        <fieldset class="full checkbox-list">
            <legend>Categories</legend>
            <?php foreach ($categories as $category): ?>
                <label><input type="checkbox" name="categories[]" value="<?= h($category['id']) ?>" <?= in_array($category['id'], $editing['categories'] ?? [], true) ? 'checked' : '' ?>> <?= h($category['name']) ?></label>
            <?php endforeach; ?>
            <?php if (empty($categories)): ?><p>Add categories before assigning them to items.</p><?php endif; ?>
        </fieldset>
        <div class="full">
            <button type="submit">Save item</button>
            <?php if ($editing): ?><a class="button secondary" href="/admin/items.php">Cancel</a><?php endif; ?>
        </div>
    </form>
</section>
<section class="panel">
    <h2>Existing Items</h2>
    <table>
        <thead><tr><th>Order</th><th>Title</th><th>Link</th><th>Actions</th></tr></thead>
        <tbody>
        <?php foreach (items_all() as $item): ?>
            <tr>
                <td><?= (int)($item['sort_order'] ?? 0) ?></td>
                <td><?= h($item['title']) ?></td>
                <td><a href="<?= h($item['link']) ?>" target="_blank" rel="noopener noreferrer">Open</a></td>
                <td class="actions">
                    <a class="button secondary" href="/admin/items.php?edit=<?= h($item['id']) ?>">Edit</a>
                    <form method="post" onsubmit="return confirm('Delete this item?');">
                        <input type="hidden" name="csrf_token" value="<?= h(csrf_token()) ?>">
                        <input type="hidden" name="action" value="delete">
                        <input type="hidden" name="id" value="<?= h($item['id']) ?>">
                        <button type="submit" class="danger">Delete</button>
                    </form>
                </td>
            </tr>
        <?php endforeach; ?>
        </tbody>
    </table>
</section>
<?php include __DIR__ . '/../includes/footer.php'; ?>
