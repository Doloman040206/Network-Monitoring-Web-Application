Write-Host "Testing web application endpoints..."
Invoke-RestMethod http://localhost:5000/health | ConvertTo-Json
Invoke-RestMethod http://localhost:5000/api/test-request | ConvertTo-Json
Invoke-RestMethod http://localhost:5000/api/stats | ConvertTo-Json
Write-Host "Done."
