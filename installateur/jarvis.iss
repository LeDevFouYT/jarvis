; L'installateur de Jarvis (Inno Setup 6), construit par l'action GitHub à chaque version :
;   python installateur/paquet.py --version X      -> installateur/charge/ (Jarvis en .pyc)
;   python installateur/python_embarque.py         -> installateur/python_embarque/ (Python officiel + get-pip.py)
;   iscc /DVersion=X installateur/jarvis.iss       -> installateur/dist/Jarvis-Installateur.exe
; Un installateur classique, pages visibles, sans droits administrateur. Les étapes longues (bibliothèques, voix,
; Ollama) tournent ensuite dans une fenêtre visible (etapes.py). Il remplace l'ancien .exe compilé par Nuitka,
; classé Trojan:Win32/Wacatac.B!ml par Defender et 10 autres antivirus (faux positif, 18/09/2026).

#ifndef Version
  #define Version "1.0.0"
#endif

[Setup]
AppId={{6B1C2E4A-7D3F-4E8B-9A15-3C0F2D7E8B41}
AppName=Jarvis
AppVersion={#Version}
AppVerName=Jarvis {#Version}
AppPublisher=LeDevFou
AppPublisherURL=https://github.com/LeDevFouYT/jarvis
AppSupportURL=https://github.com/LeDevFouYT/jarvis/issues
AppUpdatesURL=https://github.com/LeDevFouYT/jarvis/releases
VersionInfoVersion={#Version}.0
VersionInfoCompany=LeDevFou
VersionInfoDescription=Installateur de Jarvis, assistant vocal local
VersionInfoProductName=Jarvis
DefaultDirName={localappdata}\Jarvis
DefaultGroupName=Jarvis
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=dist
OutputBaseFilename=Jarvis-Installateur
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Jarvis
CloseApplications=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer un raccourci « Jarvis » sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "charge\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "python_embarque\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "etapes.py"; DestDir: "{app}"; DestName: "etapes_installation.py"; Flags: ignoreversion

[Icons]
Name: "{group}\Jarvis"; Filename: "{app}\lancer.bat"; WorkingDir: "{app}"; Comment: "Lancer Jarvis"
Name: "{group}\Désinstaller Jarvis"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Jarvis"; Filename: "{app}\lancer.bat"; WorkingDir: "{app}"; Comment: "Lancer Jarvis"; Tasks: bureau

[Run]
; fenêtre visible : chaque étape est annoncée (bibliothèques, voix, examen de la machine, Ollama)
Filename: "{app}\python\python.exe"; Parameters: """{app}\etapes_installation.py"""; WorkingDir: "{app}"; \
  StatusMsg: "Installation des bibliothèques, de la voix et d'Ollama (fenêtre à part, plusieurs minutes)…"; \
  Flags: waituntilterminated; Check: not WizardSilent
Filename: "{app}\python\python.exe"; Parameters: """{app}\etapes_installation.py"" --sans-pause"; WorkingDir: "{app}"; \
  Flags: waituntilterminated runhidden; Check: WizardSilent
Filename: "{app}\lancer.bat"; Description: "Lancer Jarvis maintenant"; WorkingDir: "{app}"; \
  Flags: postinstall nowait shellexec skipifsilent

[UninstallDelete]
; le programme et ses bibliothèques ; les réglages, les souvenirs et les fichiers de l'utilisateur restent
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\jarvis"
Type: filesandordirs; Name: "{app}\modeles"
Type: filesandordirs; Name: "{app}\cache"
Type: files; Name: "{app}\installation.log"
