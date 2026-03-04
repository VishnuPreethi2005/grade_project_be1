Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Dim baseDir
baseDir = "C:\grade_project\grade_be"

' Kill any old pythonw instances
WshShell.Run "taskkill /F /IM pythonw.exe", 0, True

' Start Python file server (hidden, skip site-packages)
WshShell.Run "C:\Users\vishn\AppData\Local\Programs\Python\Python312\pythonw.exe -S " & Chr(34) & baseDir & "\mini_ide_server_std.py" & Chr(34), 0, False
WScript.Sleep 2000

' Start Node LSP bridge (hidden)
WshShell.Run "cmd /c start /B /D " & Chr(34) & baseDir & Chr(34) & " node lsp-bridge.js", 0, False
WScript.Sleep 1000

' Start Node Docker API (hidden)
WshShell.Run "cmd /c start /B /D " & Chr(34) & baseDir & Chr(34) & " node docker_api.js", 0, False
WScript.Sleep 1000

' Open browser
WshShell.Run "cmd /c start http://localhost:8000/mini_ide", 0, False
