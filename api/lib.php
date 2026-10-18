<?php
// Zajednicke funkcije: konfiguracija, baza (MySQL na hostingu, SQLite lokalno), datumi, JSON odgovori.
date_default_timezone_set('Europe/Sarajevo');

function cfg() {
    static $c = null;
    if ($c === null) {
        $c = [
            'db'          => ['driver' => 'sqlite', 'path' => __DIR__ . '/../data/rezervacije.sqlite'],
            'admin_hash'  => '',
            'owner_email' => '',
            'mail_from'   => '',
            'site_name'   => 'Apartmani LED Vječna Vatra',
            'rates'       => ['2' => 90, '4' => 110],   // cijena po noći: 1-2 osobe / 3-4 osobe
            'max_nights'  => 30,
        ];
        $f = __DIR__ . '/config.php';
        if (is_file($f)) $c = array_replace($c, require $f);
    }
    return $c;
}

function out($data, $code = 200) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($data, JSON_UNESCAPED_UNICODE);
    exit;
}
function fail($msg, $code = 400) { out(['error' => $msg], $code); }
function body() { $j = json_decode((string)file_get_contents('php://input'), true); return is_array($j) ? $j : []; }

function db() {
    static $pdo = null;
    if ($pdo) return $pdo;
    $d = cfg()['db'];
    $opt = [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC];
    if ($d['driver'] === 'mysql') {
        $pdo = new PDO('mysql:host=' . $d['host'] . ';dbname=' . $d['name'] . ';charset=utf8mb4', $d['user'], $d['pass'], $opt);
    } else {
        if (!is_dir(dirname($d['path']))) mkdir(dirname($d['path']), 0755, true);
        $pdo = new PDO('sqlite:' . $d['path'], null, null, $opt);
    }
    migrate($pdo, $d['driver']);
    return $pdo;
}

function migrate($pdo, $driver) {
    $pk   = $driver === 'mysql' ? 'INT AUTO_INCREMENT PRIMARY KEY' : 'INTEGER PRIMARY KEY AUTOINCREMENT';
    $tail = $driver === 'mysql' ? ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4' : '';
    $pdo->exec("CREATE TABLE IF NOT EXISTS bookings (
        id $pk,
        name VARCHAR(100) NOT NULL,
        email VARCHAR(150) NOT NULL DEFAULT '',
        phone VARCHAR(40) NOT NULL DEFAULT '',
        guests VARCHAR(2) NOT NULL DEFAULT '2',
        check_in VARCHAR(10) NOT NULL,
        check_out VARCHAR(10) NOT NULL,
        price_total INT NOT NULL DEFAULT 0,
        paid_amount INT NOT NULL DEFAULT 0,
        status VARCHAR(12) NOT NULL DEFAULT 'pending',
        source VARCHAR(8) NOT NULL DEFAULT 'web',
        note VARCHAR(600) NOT NULL DEFAULT '',
        created_at VARCHAR(19) NOT NULL
    )$tail");
    $pdo->exec("CREATE TABLE IF NOT EXISTS seasons (
        id $pk,
        name VARCHAR(60) NOT NULL DEFAULT '',
        date_from VARCHAR(10) NOT NULL,
        date_to VARCHAR(10) NOT NULL,
        rate2 INT NOT NULL,
        rate4 INT NOT NULL
    )$tail");
    $pdo->exec("CREATE TABLE IF NOT EXISTS settings (
        k VARCHAR(30) NOT NULL PRIMARY KEY,
        v VARCHAR(30) NOT NULL DEFAULT ''
    )$tail");
    $pdo->exec("CREATE TABLE IF NOT EXISTS blocks (
        id $pk,
        date_from VARCHAR(10) NOT NULL,
        date_to VARCHAR(10) NOT NULL,
        note VARCHAR(200) NOT NULL DEFAULT '',
        created_at VARCHAR(19) NOT NULL
    )$tail");
}

function q($sql, $params = []) { $st = db()->prepare($sql); $st->execute($params); return $st; }

// ---- datumi: 'YYYY-MM-DD'. Rezervacija: check_in..check_out (odlazak se ne racuna kao noc). Blokada: date_from..date_to ukljucivo. ----
function valid_date($s) {
    $d = DateTime::createFromFormat('!Y-m-d', (string)$s);
    return ($d && $d->format('Y-m-d') === $s) ? $s : null;
}
function add_days($d, $n) { return (new DateTime($d))->modify(($n >= 0 ? '+' : '') . $n . ' day')->format('Y-m-d'); }
function nights_between($a, $b) { return (int)(new DateTime($a))->diff(new DateTime($b))->days; }
function each_night($from, $toExcl) {
    $o = []; $d = new DateTime($from); $e = new DateTime($toExcl);
    while ($d < $e) { $o[] = $d->format('Y-m-d'); $d->modify('+1 day'); }
    return $o;
}

// Da li se nocenja [in, out) preklapaju sa vec postojecom rezervacijom (ne otkazanom) ili blokadom?
function conflict($in, $out, $ignoreId = 0, $withBlocks = true) {
    $n = q("SELECT COUNT(*) FROM bookings WHERE status <> 'cancelled' AND check_in < ? AND check_out > ? AND id <> ?", [$out, $in, $ignoreId])->fetchColumn();
    if ($n > 0) return true;
    if (!$withBlocks) return false;
    return q("SELECT COUNT(*) FROM blocks WHERE date_from < ? AND date_to >= ?", [$out, $in])->fetchColumn() > 0;
}

// ---- cijene: osnovna cijena (config) + sezone (datumski rasponi) + doplata za vikend (pet/sub noć) + popust za duži boravak ----
function pricing_settings() {
    $d = ['weekend_extra' => 0, 'disc7' => 0, 'disc14' => 0];
    foreach (q("SELECT k, v FROM settings")->fetchAll() as $r) if (isset($d[$r['k']])) $d[$r['k']] = (int)$r['v'];
    return $d;
}
function pricing_seasons() {
    return q("SELECT id, name, date_from, date_to, rate2, rate4 FROM seasons ORDER BY date_from")->fetchAll();
}
// Ukupna cijena za nocenja [in, out) i broj osoba ('2' ili '4'). Vraca total, nights, discount (%), avg po noci.
function quote($in, $out, $g) {
    $c = cfg(); $st = pricing_settings(); $seasons = pricing_seasons();
    $sum = 0; $n = 0;
    foreach (each_night($in, $out) as $d) {
        $rate = (int)$c['rates'][$g];
        foreach ($seasons as $s) if ($d >= $s['date_from'] && $d <= $s['date_to']) { $rate = (int)($g === '2' ? $s['rate2'] : $s['rate4']); break; }
        $dow = (int)(new DateTime($d))->format('N');
        if ($dow === 5 || $dow === 6) $rate += $st['weekend_extra'];
        $sum += $rate; $n++;
    }
    $disc = $n >= 14 ? $st['disc14'] : ($n >= 7 ? $st['disc7'] : 0);
    $total = (int)round($sum * (100 - $disc) / 100);
    return ['total' => $total, 'nights' => $n, 'discount' => $disc, 'avg' => $n ? (int)round($total / $n) : 0];
}
