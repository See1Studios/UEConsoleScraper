Set ws = CreateObject("WScript.Shell")
dir = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
ws.Run """" & dir & ".venv\Scripts\pythonw.exe"" """ & dir & "ue_console_ref.py""", 0, False
