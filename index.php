<?php
require_once __DIR__ . '/includes/bootstrap.php';
$categories = categories_all();
$items = items_all();
$categoryMap = [];
foreach ($categories as $category) {
    $categoryMap[$category['id']] = $category['name'];
}
$selectedCategory = $_GET['category'] ?? '';
if ($selectedCategory !== '') {
    $items = array_values(array_filter($items, static function ($item) use ($selectedCategory) {
        return in_array($selectedCategory, $item['categories'] ?? [], true);
    }));
}
include __DIR__ . '/includes/header.php';
?>
<section class="hero">
    <h1>Application Directory</h1>
    <p>Browse configured applications and links by category.</p>
</section>

<form class="filter" method="get">
    <label for="category">Filter by category</label>
    <select id="category" name="category" onchange="this.form.submit()">
        <option value="">All categories</option>
        <?php foreach ($categories as $category): ?>
            <option value="<?= h($category['id']) ?>" <?= $selectedCategory === $category['id'] ? 'selected' : '' ?>><?= h($category['name']) ?></option>
        <?php endforeach; ?>
    </select>
    <noscript><button type="submit">Apply</button></noscript>
</form>

<?php if (empty($items)): ?>
    <p class="empty">No entries have been added yet.</p>
<?php else: ?>
    <div class="cards">
        <?php foreach ($items as $item): ?>
            <article class="card">
                <div class="card-order">#<?= (int)($item['sort_order'] ?? 0) ?></div>
                <h2><a href="<?= h($item['link']) ?>" target="_blank" rel="noopener noreferrer"><?= h($item['title']) ?></a></h2>
                <p><?= nl2br(h($item['description'] ?? '')) ?></p>
                <?php if (!empty($item['credentials'])): ?>
                    <div class="credentials">
                        <h3>Credentials</h3>
                        <?php foreach ($item['credentials'] as $credential): ?>
                            <dl>
                                <dt>Username</dt>
                                <dd><code><?= h($credential['username'] ?? '') ?></code></dd>
                                <dt>Password</dt>
                                <dd><code><?= h($credential['password'] ?? '') ?></code></dd>
                            </dl>
                        <?php endforeach; ?>
                    </div>
                <?php endif; ?>
                <div class="tags">
                    <?php foreach (($item['categories'] ?? []) as $categoryId): ?>
                        <?php if (isset($categoryMap[$categoryId])): ?>
                            <span><?= h($categoryMap[$categoryId]) ?></span>
                        <?php endif; ?>
                    <?php endforeach; ?>
                </div>
            </article>
        <?php endforeach; ?>
    </div>
<?php endif; ?>
<?php include __DIR__ . '/includes/footer.php'; ?>
