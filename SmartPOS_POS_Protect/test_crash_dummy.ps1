$code = @'
using System; class X {static void Main(){ Environment.FailFast("TestCrash"); }}
'@
Add-Type -TypeDefinition $code -Language CSharp -OutputAssembly "$env:TEMP\CrashIt.exe"
& "$env:TEMP\CrashIt.exe"