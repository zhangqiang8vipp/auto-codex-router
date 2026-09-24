' Launch a command without creating a console window. The scheduled task uses
' this windowless host because PowerShell's -WindowStyle Hidden can still flash
' its console during process startup on an interactive desktop.
Option Explicit

Dim shell, command, index
If WScript.Arguments.Count < 1 Then WScript.Quit 2

command = QuoteArgument(WScript.Arguments(0))
For index = 1 To WScript.Arguments.Count - 1
  command = command & " " & QuoteArgument(WScript.Arguments(index))
Next

Set shell = CreateObject("WScript.Shell")
WScript.Quit shell.Run(command, 0, True)

Function QuoteArgument(value)
  QuoteArgument = Chr(34) & value & Chr(34)
End Function
