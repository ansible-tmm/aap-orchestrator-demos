<?php
header('Content-Type: application/json');
if ($_SERVER['REQUEST_METHOD'] !== 'POST' || empty($_FILES['invoice'])) { http_response_code(400); echo json_encode(['ok'=>false,'error'=>'no file']); exit; }
$f = $_FILES['invoice'];
echo json_encode(['ok'=>$f['error']===UPLOAD_ERR_OK,'name'=>basename($f['name']),'bytes'=>$f['size'],'error'=>$f['error']]);
