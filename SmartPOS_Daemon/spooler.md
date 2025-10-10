Invoke-RestMethod http://127.0.0.1:7077/faults/create -Method POST -Body (@{ kind="sticky_queue" } | ConvertTo-Json) -ContentType 'application/json'

$req = @{ ticket_id="DBG-PR0018"; problem_code="PR0018"; device=@{ type="receipt_printer" } } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:7077/action/run -Method POST -Body $req -ContentType 'application/json'

$req = @{
  ticket_id    = "DBG-PR0018B"
  problem_code = "PR0018"
  device       = @{ type="receipt_printer" }
  context      = @{ beautify = $true }
} | ConvertTo-Json

Invoke-RestMethod http://127.0.0.1:7077/action/run -Method POST -Body $req -ContentType 'application/json'
