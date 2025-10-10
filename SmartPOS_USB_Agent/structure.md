# Структура проекта SmartPOS USB Agent

```text
╤ЄЁєъЄєЁр яряюъ Єюьр OS
╤хЁшщэ√щ эюьхЁ Єюьр: 6460-0EA2
C:.
|   structure.md
|  
+---dist
+---docs
|   |   API-ъы■ўш.docx
|   |   config-json-ёЄЁєъЄєЁр ш эрёЄЁющъш.docx
|   |   Examples Pack_readme And Samples.docx
|   |   Pack_build Zip Guide.pdf
|   |   Poller - ры№ЄхЁэрЄшт√ яю яюфяшёъх.docx
|   |   Readme Cashiers Pos Quick Aid.docx
|   |   Readme Engineers Usb Dev Ctl.docx
|   |   Readme Full.pdf
|   |   readme_full.md
|   |   Smart Pos Usb Agent V1.4.docx
|   |   Smart Pos Usb Pilot Package.docx
|   |   Smart Pos Usb Reliability Architecture V1 (ъюэЎхяЄ).docx
|   |   Tests_hand Tests.docx
|   |   ╧ЁютхЁъш ЁрсюЄ√ Watchdog.docx
|  
|   |---ops
|           README_ops_short.docx
|           README_ops_short.md
|  
+---examples_pack
|       examples_pack_readme_and_samples.md
|  
+---installer
|   +---assets
|   |       SmartPOS_USB_Agent.ico.txt
|   |  
|   +---inno
|   |       SmartPOS_USB_Agent.iss
|   |  
|   +---scripts
|   |       install_service.ps1
|   |       uninstall_service.ps1
|   |  
|   |---wix
|           SmartPOS_USB_Agent.wxs
|  
+---src
|   +---dotnet
|   |   |---SmartPOS.UsbTray
|   |           smart_pos_usb_tray.txt
|   |           smart_pos_usb_tray3.txt
|   |           smart_pos_usb_tray4.txt
|   |           smart_pos_usb_tray_program.cs
|   |           smart_pos_usb_tray_smart_pos_usb_tray.txt
|   |           smart_pos_usb_tray_v_2.txt
|   |           smart_pos_usb_tray_win_forms.cs
|   |  
|   |---python
|       |   run_usb_devctl.bat
|       |   smartpos_usb_service_v14.py
|       |   trace_wrappers_v2.py
|       |   usb_agent_core.py
|       |   usb_agent_smoketests.py
|       |   usb_devctl_cli.py
|       |  
|       +---db
|       |       smartpos_usb.db
|       |       smartpos_usb.db-shm
|       |       smartpos_usb.db-wal
|       |       smartpos_usb.db.bak_20251003_195540
|       |  
|       +---helpers
|       |       __init__.py
|       |  
|       +---logs
|       |       service.log
|       |  
|       |---__pycache__
|               trace_wrappers_v2.cpython-311.pyc
|               usb_agent_core.cpython-311.pyc
|  
+---tests
|       test_cli_export_smoke.py
|       test_config_and_hot_reload.py
|       test_export_zip_mask.py
|       test_sqlite_retention.py
|       usb_agent_autotests.py
|  
|---tools
    |   install_watchdog.ps1
    |   make_release_zip.ps1
    |   Test-InnoIss.ps1
    |   uninstall_watchdog.ps1
    |  
    |---ux
            config.json
            service_name_map.json
            SmartPOS-USB-UX.ps1
```
