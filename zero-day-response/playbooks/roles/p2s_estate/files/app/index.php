<?php $svc = getenv('P2S_SERVICE') ?: 'demo-service'; ?>
<!doctype html><html><head><meta charset="utf-8"><title><?= htmlspecialchars($svc) ?></title>
<style>body{font-family:system-ui,sans-serif;max-width:640px;margin:48px auto;padding:0 16px;color:#1f1f1f}
.card{border:1px solid #ddd;border-radius:8px;padding:20px}code{background:#f3f3f3;padding:2px 4px}</style></head>
<body><h1><?= htmlspecialchars($svc) ?></h1>
<div class="card"><p>Upload an invoice (PDF, max 2&nbsp;MB)</p>
<form action="upload.php" method="post" enctype="multipart/form-data">
<input type="file" name="invoice"> <button type="submit">Upload</button></form></div>
<p style="color:#666;font-size:13px">PHP <?= PHP_VERSION ?> &middot; SAPI <code><?= php_sapi_name() ?></code></p>
</body></html>
