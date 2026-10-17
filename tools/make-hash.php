<?php
// Upotreba: php tools/make-hash.php "lozinka"  -> ispisuje hash za admin_hash u api/config.php
if (PHP_SAPI !== 'cli' || empty($argv[1])) { fwrite(STDERR, "Upotreba: php tools/make-hash.php \"lozinka\"\n"); exit(1); }
echo password_hash($argv[1], PASSWORD_DEFAULT), "\n";
