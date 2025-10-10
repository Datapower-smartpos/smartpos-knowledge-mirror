param([string[]]$Services=@('Spooler','Winmgmt'))
foreach($s in $Services){
sc.exe failure $s reset= 3600 actions= restart/5000/restart/10000//
sc.exe failureflag $s 1
}
Write-Host "[OK] Recovery set for: $($Services -join ', ')"