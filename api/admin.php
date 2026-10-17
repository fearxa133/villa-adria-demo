<?php
// Admin API: prijava, rezervacije, blokade datuma, placanja, statistika. Sve osim prijave trazi sesiju.
require __DIR__ . '/lib.php';
session_name('adm');
session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'httponly' => true, 'samesite' => 'Lax', 'secure' => !empty($_SERVER['HTTPS'])]);
session_start();

$action = $_GET['action'] ?? '';
$post   = $_SERVER['REQUEST_METHOD'] === 'POST';
$in     = $post ? body() : [];
$c      = cfg();

if ($action === 'me') out(['auth' => !empty($_SESSION['admin']), 'csrf' => $_SESSION['csrf'] ?? '', 'rates' => !empty($_SESSION['admin']) ? $c['rates'] : null]);

if ($action === 'login') {
    if (!$post) fail('Metoda nije dozvoljena.', 405);
    if (!$c['admin_hash']) fail('Admin lozinka nije postavljena u api/config.php.', 500);
    if (!password_verify((string)($in['password'] ?? ''), $c['admin_hash'])) { sleep(1); fail('Pogrešna lozinka.', 401); }
    session_regenerate_id(true);
    $_SESSION['admin'] = true;
    $_SESSION['csrf']  = bin2hex(random_bytes(16));
    out(['ok' => true, 'csrf' => $_SESSION['csrf'], 'rates' => $c['rates']]);
}

if (empty($_SESSION['admin'])) fail('Niste prijavljeni.', 401);
if ($post && !hash_equals($_SESSION['csrf'], $_SERVER['HTTP_X_CSRF'] ?? '')) fail('Neispravan sigurnosni token. Osvježite stranicu.', 403);

switch ($action) {
case 'logout':
    session_destroy();
    out(['ok' => true]);

case 'bookings':
    out(['bookings' => q("SELECT * FROM bookings ORDER BY check_in DESC, id DESC")->fetchAll()]);

case 'booking_save':
    // Kreira novu (bez id) ili mijenja postojecu; polja koja nisu poslana ostaju kakva jesu.
    $id  = (int)($in['id'] ?? 0);
    $cur = ['name' => '', 'email' => '', 'phone' => '', 'guests' => '2', 'check_in' => '', 'check_out' => '', 'price_total' => null, 'paid_amount' => 0, 'status' => 'confirmed', 'note' => ''];
    if ($id) {
        $row = q("SELECT * FROM bookings WHERE id = ?", [$id])->fetch();
        if (!$row) fail('Rezervacija ne postoji.', 404);
        $cur = array_intersect_key($row, $cur);
    }
    foreach ($cur as $k => $_) if (array_key_exists($k, $in)) $cur[$k] = is_string($in[$k]) ? trim($in[$k]) : $in[$k];
    if (mb_strlen($cur['name']) < 2 || mb_strlen($cur['name']) > 100) fail('Unesite ime.');
    if ($cur['email'] !== '' && !filter_var($cur['email'], FILTER_VALIDATE_EMAIL)) fail('Email nije ispravan.');
    if (!isset($c['rates'][(string)$cur['guests']])) fail('Neispravan broj osoba.');
    if (!in_array($cur['status'], ['pending', 'confirmed', 'cancelled'], true)) fail('Neispravan status.');
    if (!valid_date($cur['check_in']) || !valid_date($cur['check_out']) || $cur['check_out'] <= $cur['check_in']) fail('Neispravni datumi.');
    if (mb_strlen($cur['note']) > 600) fail('Napomena je predugačka.');
    $nights = nights_between($cur['check_in'], $cur['check_out']);
    if ($cur['price_total'] === null || $cur['price_total'] === '') $cur['price_total'] = $nights * (int)$c['rates'][(string)$cur['guests']];
    $cur['price_total'] = (int)$cur['price_total']; $cur['paid_amount'] = (int)$cur['paid_amount'];
    if ($cur['price_total'] < 0 || $cur['paid_amount'] < 0) fail('Iznosi ne mogu biti negativni.');
    if ($cur['status'] !== 'cancelled' && conflict($cur['check_in'], $cur['check_out'], $id)) fail('Termin se preklapa sa drugom rezervacijom ili blokiranim danima.', 409);
    if ($id) {
        q("UPDATE bookings SET name=?, email=?, phone=?, guests=?, check_in=?, check_out=?, price_total=?, paid_amount=?, status=?, note=? WHERE id=?",
          [$cur['name'], $cur['email'], $cur['phone'], (string)$cur['guests'], $cur['check_in'], $cur['check_out'], $cur['price_total'], $cur['paid_amount'], $cur['status'], $cur['note'], $id]);
    } else {
        q("INSERT INTO bookings (name, email, phone, guests, check_in, check_out, price_total, paid_amount, status, source, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,'admin',?,?)",
          [$cur['name'], $cur['email'], $cur['phone'], (string)$cur['guests'], $cur['check_in'], $cur['check_out'], $cur['price_total'], $cur['paid_amount'], $cur['status'], $cur['note'], date('Y-m-d H:i:s')]);
        $id = (int)db()->lastInsertId();
    }
    out(['ok' => true, 'id' => $id]);

case 'booking_delete':
    q("DELETE FROM bookings WHERE id = ?", [(int)($in['id'] ?? 0)]);
    out(['ok' => true]);

case 'blocks':
    out(['blocks' => q("SELECT * FROM blocks ORDER BY date_from DESC")->fetchAll()]);

case 'block_add':
    // Blokada = dani zauzeti dogovorom van sajta; date_to je ukljucen (zadnja zauzeta noc).
    $f = valid_date($in['date_from'] ?? ''); $t = valid_date($in['date_to'] ?? '');
    if (!$f || !$t || $t < $f) fail('Neispravni datumi.');
    if (conflict($f, add_days($t, 1), 0, false)) fail('U tom periodu već postoji rezervacija. Prvo je otkažite ili izmijenite.', 409);
    q("INSERT INTO blocks (date_from, date_to, note, created_at) VALUES (?,?,?,?)", [$f, $t, mb_substr(trim((string)($in['note'] ?? '')), 0, 200), date('Y-m-d H:i:s')]);
    out(['ok' => true]);

case 'block_delete':
    q("DELETE FROM blocks WHERE id = ?", [(int)($in['id'] ?? 0)]);
    out(['ok' => true]);

case 'stats':
    // Po mjesecu (prema datumu dolaska): potvrdjene rezervacije, nocenja, ocekivano i naplaceno; blokirane noci posebno.
    $m = [];
    $slot = function ($k) use (&$m) { if (!isset($m[$k])) $m[$k] = ['month' => $k, 'bookings' => 0, 'pending' => 0, 'nights' => 0, 'expected' => 0, 'paid' => 0, 'blocked' => 0]; };
    foreach (q("SELECT * FROM bookings WHERE status <> 'cancelled'")->fetchAll() as $r) {
        $k = substr($r['check_in'], 0, 7); $slot($k);
        if ($r['status'] === 'pending') { $m[$k]['pending']++; continue; }
        $m[$k]['bookings']++; $m[$k]['expected'] += (int)$r['price_total']; $m[$k]['paid'] += (int)$r['paid_amount'];
        foreach (each_night($r['check_in'], $r['check_out']) as $d) { $dk = substr($d, 0, 7); $slot($dk); $m[$dk]['nights']++; }
    }
    foreach (q("SELECT * FROM blocks")->fetchAll() as $r) {
        foreach (each_night($r['date_from'], add_days($r['date_to'], 1)) as $d) { $dk = substr($d, 0, 7); $slot($dk); $m[$dk]['blocked']++; }
    }
    ksort($m);
    out(['months' => array_values($m), 'cancelled' => (int)q("SELECT COUNT(*) FROM bookings WHERE status = 'cancelled'")->fetchColumn()]);

default:
    fail('Nepoznata akcija.', 404);
}
