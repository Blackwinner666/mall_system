Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\mall_system"
WshShell.Run """C:\Users\Administrator\AppData\Local\Programs\Python\Python311\pythonw.exe""" & " C:\mall_system\app.py", 0, False
