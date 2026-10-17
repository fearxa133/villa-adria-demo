<?php
// Javni endpoint: koje su noci zauzete (bez ikakvih licnih podataka) + cjenovnik.
require __DIR__ . '/lib.php';
$today = date('Y-m-d');
$limit = add_days($today, 730);
$set = [];
foreach (q("SELECT check_in, check_out FROM bookings WHERE status <> 'cancelled' AND check_out > ?", [$today])->fetchAll() as $r) {
    foreach (each_night(max($r['check_in'], $today), min($r['check_out'], $limit)) as $d) $set[$d] = 1;
}
foreach (q("SELECT date_from, date_to FROM blocks WHERE date_to >= ?", [$today])->fetchAll() as $r) {
    foreach (each_night(max($r['date_from'], $today), min(add_days($r['date_to'], 1), $limit)) as $d) $set[$d] = 1;
}
$booked = array_keys($set); sort($booked);
header('Cache-Control: no-store');
out(['booked' => $booked, 'rates' => cfg()['rates'], 'today' => $today, 'max_nights' => cfg()['max_nights']]);
