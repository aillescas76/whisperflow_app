Cookie Policy

Notebooks
Computers / PCs
Accesories
B2B
New

Settings
German
English
Customer account
Register
PRIME GPU Render Offloading/GPU on-demand Mode Guide
2022-12-20 13:02:54
Our laptops typically have an integrated GPU (iGPU) that conserves battery power and a more powerful, but also more power-hungry, dedicated GPU (dGPU). You can run the entire system on one or the other GPU, depending on your needs. However, switching between them requires restarting the PC. Alternatively, you can let the desktop environment and other programs that don't require much graphics power handle the iGPU and only activate the dGPU for specific games and programs that need it. This technology is called "  dGPU" 

in Windows OPTIMUSand Linux . PRIME GPU Render OffloadingGPU on-demand Mode
validity
This is a short guide on how to use PRIME. The sections "Preparation (TUXEDO OS/Ubuntu(-derivative))" and "Start Menu and Desktop Shortcuts (TUXEDO OS/Ubuntu(-derivative) WebFAI with KDE Plasma)" refer specifically to TUXEDO OS and/or WebFAI installations. All other explanations in this guide apply to all Linux distributions, including those not based on Ubuntu.
Requirements
This guide applies only if the proprietary NVIDIA driver 470.xx or later, or an open-source driver (amdgpu (AMD/Radeon), nouveau (NVIDIA), i915 (Intel)) is used. It explicitly does not work if the proprietary NVIDIA driver 390.xx or earlier, or the old open-source "radeon" driver, is used. This means that an NVIDIA GeForce 800M or later, or an AMD Radeon R9 or later, is required as the dedicated GPU.
Preparation (TUXEDO OS/Ubuntu (derivative))
1. Activate the PRIME/on-demand-mode with:
sudo prime-select on-demand

2. Install  tuxedo-dgpu-runusing:
sudo apt install tuxedo-dgpu-run

3. Restart your PC.

The desktop environment will now run on the iGPU, but the dGPU can be activated for individual programs at any time.
command line
For TUXEDO_OS/Ubuntu(-derivatives) / WebFAI: Execute the command by entering the following:
dgpu-run «der auszuführende Befehl»

For other distributions: The dGPU is used when the environment variables __NV_PRIME_RENDER_OFFLOAD=1, __VK_LAYER_NV_optimus=NVIDIA_only, __GLX_VENDOR_LIBRARY_NAME=nvidiaand DRI_PRIME=1are set with the following command: 
__NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia DRI_PRIME=1 «der auszuführende Befehl»

A brief explanation of what the variables do:
__NV_PRIME_RENDER_OFFLOAD=1
Vulkan: Enables the implicit overlay for offloading on NVIDIA (which reorders the available GPUs so that the NVIDIA dGPUs come first)
OpenGL: Ensure that NVIDIA's implementation checks if it is running on a PRIME device (and thus prevents it from crashing in this case).
__VK_LAYER_NV_optimus=NVIDIA_only
Vulkan: Ensure that the implicit overlay for offloading to NVIDIA removes all non-NVIDIA GPUs from the availability list (optional)
__GLX_VENDOR_LIBRARY_NAME=nvidia
OpenGL: Use NVIDIA's OpenGL implementation (i.e., use the proprietary NVIDIA driver and not Mesa, which only supports open source drivers, e.g., i915, AMDGPU, and Nouveau)
DRI_PRIME=1
Start menu and desktop shortcuts (TUXEDO_OS/Ubuntu(-derivative) WebFAI with KDE Plasma)
Right-click on a program shortcut Starte Applikation mit diskreter GPU/Run application with discrete GPU. However, this may not work for shortcuts created by different launchers. In this case, either the launcher itself must be started on the dGPU, or you must configure within the launcher which programs should run using the dGPU. Instructions for all launchers we know of that are supported on Linux are provided below.
 Steam
1. Open the Eigenschaften/Propertiesgame/program.

2. In the field Startoptionen/Launch Optionson the Allgemein/General-tab, enter the following: Please ensure that this is at the beginning of the line if another entry already exists there.

__NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia DRI_PRIME=1 %command%


 Lutris
1. In Lutris, select Konfigurieren/Configurethe game/program. 2. Activate the option in the tab. 3. Press  .

Aktiviere/Enable NVIDIA Prime Render OffloadSystemeinstellungen/System options

Speichern/Save
 Heroic
1. Open the Einstellungen/Settingsgame's settings. 2. In the `-tab` field, add the following: For PRIME devices with a discrete AMD GPU, or when using Nouveau, this variable should be sufficient. The other three variables are ignored if the proprietary NVIDIA driver is not installed.

Erweiterte Optionen (Umgebungsvariablen)/Advanced Options (Environment Variables)Andere/Other

__NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia DRI_PRIME=1


  Bottles
1. Select the bottle containing the game/program. 2. Select the game/program. 3. In the field, enter the following:  Please ensure this is at the beginning of the line if another entry already exists there. 4. Press Enter .

Change launch options



__NV_PRIME_RENDER_OFFLOAD=1 __VK_LAYER_NV_optimus=NVIDIA_only __GLX_VENDOR_LIBRARY_NAME=nvidia DRI_PRIME=1 %command%




Save
 Mini Galaxy
Menu entries/shortcuts created by Minigalaxy, unlike those created by other launchers, function using the method described in the "Start Menu and Desktop Shortcuts" section. Therefore, please do not launch games/programs installed via Minigalaxy using the launcher interface, but instead create a shortcut and run it on the dGPU as described above. To enable Minigalaxy to create menu entries/shortcuts, follow these instructions before installing a game:

1. Select from the hamburger menu Einstellungen/preferences. 2. Activate . 3. Click on . 4. Install the desired game.

Menü-Verknüpfungen erstellen/Create menu shortcuts

Speichern/Save


 PlayOnLinux
Shortcuts created by PlayOnLinux, unlike those created by other launchers, work using the method described in the "Start Menu and Desktop Shortcuts" section. Therefore, please do not launch games/programs installed via PlayOnLinux using the launcher interface, but instead create a shortcut and run it on the dGPU as described above.
Rare
Rare currently does not allow you to set individual environment variables for each game (this feature will be added in a future release).
To use the dGPU anyway:
1. If Rare is running: Quit Rare completely (including closing the system tray icon in the system bar).
2. Launch Rare on the dGPU (see the "Command Line" or "Start Menu and Desktop Shortcuts" sections).
3. Launch the game.
4. Quit Rare completely after the game is finished. Otherwise, the dGPU will remain powered on and continue to consume power.
 GameHub
GameHub currently does not allow for easy customization of individual game launch options (this feature is being worked on and may be included in a future version).
To use the dGPU anyway:
1. If GameHub is running: Close GameHub completely.
2. Launch GameHub on the dGPU (see "Command Line" or "Start Menu and Desktop Shortcuts"). 3.
Launch the game
. 4. Close GameHub completely after the game has finished. Otherwise, the dGPU will remain powered on and continue to consume power.
itch
Itch currently does not allow you to set individual launch options for each game.
To use the dGPU anyway:
1. If itch is running: Quit it completely (including closing the icon in the system tray).
2. Launch it on the dGPU (see "Command Line" or "Start Menu and Desktop Shortcuts").
3. Launch the game.
4. Quit it completely again after the game is finished. Otherwise, the dGPU will remain powered on and continue to consume power.
Pegasus Frontend
Unfortunately, Pegasus Frontend currently does not allow you to set individual launch options for each game. To use the dGPU for games it launches directly:
1. If Pegasus Frontend is running: Close Pegasus Frontend.
2. Launch Pegasus Frontend on the dGPU (see "Command Line" or "Start Menu and Desktop Shortcuts").
3. Launch the game.
4. Close Pegasus Frontend after the game has finished. Otherwise, the dGPU will remain powered on and continue to consume electricity.
If Pegasus Frontend does not launch the game directly, but instead uses a method like Steam, please refer to the explanation for Steam above.

Windows Launcher via Wine (Epic Games Store, Origin, Ubisoft Connect, etc.)
Due to the availability of better alternatives like Lutris and Heroic, we advise against using the Windows Launcher directly via Wine. Even in Lutris, for example, the Epic Games Store should not be installed and used directly; instead, games should be installed individually. In this case, Lutris installs the Epic Games Store itself in the background, if needed, and the games remain cleanly separated, allowing Lutris to apply an individual Wine configuration for each game.

If you still wish to use a Windows Launcher directly and enable PRIME, the procedure is the same as with other launchers that do not allow individual launch options per game (itch, Pegasus Frontend). This is due to the design, as these options must be set before Wine is started.

 
Image of Tux, the Linux mascot

Linux compatible
stylized badge for guarantee

Up to 5 years warranty
stylized image of a rocket

Ready for immediate use
Image of Germany with a wrench in the center

Made in Germany
Image of Germany with paragraph symbol in the middle

German data protection
stylized image of a support worker

German Tech Support
Advice
Advice & Support
B2B

Mon - Fri: 9am-1pm & 2pm-5pm
+49 (0) 821 / 8998 2992

About TUXEDO
Why TUXEDO?
TUXEDO Control Center
TUXEDO Tomte
TUXEDO WebFAI
TUXEDO OS
TUXEDO Aquaris
Custom logos and keyboards
Help & Support
Downloads & Drivers
System diagnostics
Frequently Asked Questions (FAQ)
Instructions
Help for my device
Right of withdrawal
Shipping costs & delivery times
Payment methods
News & more
News & Blog
Press & PR
Newsletter
Event calendar
Jobs & Careers
Sponsorship
Community


Your Linux specialist since 2004
Accessibility
Data protection
imprint
Battery disposal
Terms and Conditions
