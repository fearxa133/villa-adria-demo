<?php
// Javni endpoint: cijena za odabrani termin (sezone, vikend, popust za duži boravak).
require __DIR__ . '/lib.php';
$c  = cfg();
$ci = valid_date($_GET['in'] ?? ''); $co = valid_date($_GET['out'] ?? ''); $g = (string)($_GET['g'] ?? '');
if (!$ci || !$co || $co <= $ci || !isset($c['rates'][$g])) fail('Neispravan upit.');
if (nights_between($ci, $co) > $c['max_nights']) fail('Predugo.');
out(quote($ci, $co, $g));
