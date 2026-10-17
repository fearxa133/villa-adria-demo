<?php
// Kopirajte u api/config.php i popunite. config.php se NE objavljuje na git.
// Lozinku za admin generisite sa: php tools/make-hash.php "vasa-lozinka"
return [
    // Na hostingu (MySQL iz cPanel-a):
    'db' => ['driver' => 'mysql', 'host' => 'localhost', 'name' => 'cpaneluser_rezervacije', 'user' => 'cpaneluser_rez', 'pass' => '...'],
    // Lokalno (SQLite, bez podesavanja) - samo izbrisite 'db' red iznad.
    'admin_hash'  => '',                       // rezultat tools/make-hash.php
    'owner_email' => 'rezervacije@vasadomena.ba',   // ovdje stizu obavijesti o novim rezervacijama
    'mail_from'   => 'Apartmani <rezervacije@vasadomena.ba>',
    'rates'       => ['2' => 90, '4' => 110],  // KM po noci: 1-2 osobe / 3-4 osobe
    'max_nights'  => 30,
];
