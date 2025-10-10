param([string]$PrinterName = "POS_Receipt")
Add-Type -AssemblyName System.Drawing
$printDoc = New-Object System.Drawing.Printing.PrintDocument
$printDoc.PrinterSettings.PrinterName = $PrinterName
$printDoc.PrintController = New-Object System.Drawing.Printing.StandardPrintController
$printDoc.add_PrintPage({ param($sender,$e)
    $e.Graphics.DrawString("STICKY", (New-Object System.Drawing.Font("Consolas", 10)), [System.Drawing.Brushes]::Black, 1, 1)
    $e.HasMorePages = $true  # намеренно застрянет
})
$printDoc.Print()
Write-Host "Injected sticky job to $PrinterName"
