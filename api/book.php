<?php
// Javni endpoint: gost salje zahtjev za rezervaciju (status "na cekanju").
require __DIR__ . '/lib.php';
if ($_SERVER['REQUEST_METHOD'] !== 'POST') fail('Metoda nije dozvoljena.', 405);
$in = body();
if (!empty($in['website'])) out(['ok' => true]);            // honeypot: botovi popune skriveno polje

$c     = cfg();
$name  = trim((string)($in['name'] ?? ''));
$email = trim((string)($in['email'] ?? ''));
$phone = trim((string)($in['phone'] ?? ''));
$note  = trim((string)($in['note'] ?? ''));
$g     = (string)($in['guests'] ?? '');
$ci    = valid_date($in['check_in'] ?? '');
$co    = valid_date($in['check_out'] ?? '');

if (mb_strlen($name) < 2 || mb_strlen($name) > 100) fail('Unesite ime i prezime.');
if (!filter_var($email, FILTER_VALIDATE_EMAIL) || strlen($email) > 150) fail('Unesite ispravnu email adresu.');
if (strlen($phone) > 40 || !preg_match('/^[0-9 +()\/.-]*$/', $phone)) fail('Telefon nije ispravan.');
if (mb_strlen($note) > 500) fail('Napomena je predugačka.');
if (!isset($c['rates'][$g])) fail('Odaberite broj osoba.');
if (!$ci || !$co) fail('Odaberite datum dolaska i odlaska.');
if ($ci < date('Y-m-d')) fail('Datum dolaska je u prošlosti.');
$nights = $co > $ci ? nights_between($ci, $co) : 0;
if ($nights < 1) fail('Odlazak mora biti poslije dolaska.');
if ($nights > $c['max_nights']) fail('Najduži boravak je ' . $c['max_nights'] . ' noći. Za duže javite se direktno.');
if (q("SELECT COUNT(*) FROM bookings WHERE email = ? AND status = 'pending'", [$email])->fetchColumn() >= 3) fail('Već imate nekoliko upita na čekanju. Sačekajte potvrdu.', 429);

$pdo = db();
$pdo->beginTransaction();
if (conflict($ci, $co)) { $pdo->rollBack(); fail('Taj termin je u međuvremenu zauzet. Odaberite drugi.', 409); }
$price = quote($ci, $co, $g)['total'];
q("INSERT INTO bookings (name, email, phone, guests, check_in, check_out, price_total, status, source, note, created_at) VALUES (?,?,?,?,?,?,?,'pending','web',?,?)",
  [$name, $email, $phone, $g, $ci, $co, $price, $note, date('Y-m-d H:i:s')]);
$id = $pdo->lastInsertId();
$pdo->commit();

if ($c['owner_email']) {
    $subj = '=?UTF-8?B?' . base64_encode('Nova rezervacija: ' . $name . ' (' . $ci . ' - ' . $co . ')') . '?=';
    $msg  = "Nova rezervacija na čekanju (#$id)\n\nIme: $name\nEmail: $email\nTelefon: $phone\nOsoba: " . ($g === '2' ? '1-2' : '3-4')
          . "\nDolazak: $ci\nOdlazak: $co\nNoći: $nights\nOkvirna cijena: $price KM\nNapomena: $note\n";
    $h = "Content-Type: text/plain; charset=UTF-8\r\nReply-To: $email\r\n";
    if ($c['mail_from']) $h .= 'From: ' . $c['mail_from'] . "\r\n";
    @mail($c['owner_email'], $subj, $msg, $h);
}
out(['ok' => true, 'id' => (int)$id, 'nights' => $nights, 'price' => $price]);
