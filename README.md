This is a very early stage of the program. Hard-Coded paths for memory, iDRAC IP, and Login credentials.

program requiring the use of an external program (impi, and the harder to find impi.exe if your running windows). 
Once impi is installed, and reachable to the system (try to use 'impi' in CMD / Terminal, you should get a responce saying to use a target IP)

I Included the neccisary variable, 'debug' in case it doesnt work for others.

-----------------
Future Plans:
  Integrade one-time user definition for the data path, for login credentials, and various data saved from the script.
  add a settings menu for default modes, temp-curve to use, etc
  Encode the file containing login info, for security reasons.
  Freshen up the UI
  Automaticly attach itself to the startup sequence, and for windows users, hide in the taskbar.
  