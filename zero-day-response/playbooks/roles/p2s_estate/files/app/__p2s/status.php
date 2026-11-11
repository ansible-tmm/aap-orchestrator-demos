<?php
// Demo verification endpoint: reports the EFFECTIVE runtime settings (not config files).
// Blocked at the edge and restricted to local/management access on each host.
header('Content-Type: application/json');
$keys = ['session.upload_progress.enabled','post_max_size','upload_max_filesize','memory_limit','fatal_error_backtraces'];
$ini = [];
foreach ($keys as $k) { $v = ini_get($k); $ini[$k] = ($v === false) ? null : $v; }
echo json_encode(['php_version'=>PHP_VERSION,'sapi'=>php_sapi_name(),'pid'=>getmypid(),
  'started'=>@filemtime('/proc/'.getmypid()),'ini'=>$ini,'service'=>getenv('P2S_SERVICE') ?: null]);
