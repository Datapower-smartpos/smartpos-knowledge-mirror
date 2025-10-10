.\
│   pytest.ini
│   structure.md
│   structure_clean.md
│
├───.pytest_cache
│   │   .gitignore
│   │   CACHEDIR.TAG
│   │   README.md
│   │
│   └───v
│       └───cache
│               lastfailed
│               nodeids
│
├───dist
│       pytest-report.xml
│
├───docs
│   │   API-ключи.docx
│   │   config-json-структура и настройки.docx
│   │   Examples Pack_readme And Samples.docx
│   │   Pack_build Zip Guide.pdf
│   │   Poller - альтернативы по подписке.docx
│   │   Readme Cashiers Pos Quick Aid.docx
│   │   Readme Engineers Usb Dev Ctl.docx
│   │   Readme Full.pdf
│   │   readme_full.md
│   │   Smart Pos Usb Agent V1.4.docx
│   │   Smart Pos Usb Reliability Architecture V1 (концепт).docx
│   │   SmartPOS_USB_Agent_тестирование.docx
│   │   tests_expected_fails_and_repair.md
│   │   Tests_hand Tests.docx
│   │   Проверки работы Watchdog.docx
│   │
│   └───ops
│           README_ops_short.docx
│           README_ops_short.md
│
├───examples_pack
│       examples_pack_readme_and_samples.md
│
├───installer
│   ├───assets
│   │       SmartPOS_USB_Agent.ico.txt
│   │
│   ├───inno
│   │   │   SmartPOS_USB_Agent.iss
│   │   │
│   │   └───Output
│   │           SmartPOS_USB_Agent_1.4.1_Setup.exe
│   │
│   ├───scripts
│   │       install_service.ps1
│   │       uninstall_service.ps1
│   │
│   └───wix
│           SmartPOS_USB_Agent.wxs
│
├───src
│   ├───dotnet
│   │   └───SmartPOS.UsbTray
│   │           smart_pos_usb_tray.txt
│   │           smart_pos_usb_tray3.txt
│   │           smart_pos_usb_tray4.txt
│   │           smart_pos_usb_tray_program.cs
│   │           smart_pos_usb_tray_smart_pos_usb_tray.txt
│   │           smart_pos_usb_tray_v_2.txt
│   │           smart_pos_usb_tray_win_forms.cs
│   │
│   └───python
│       │   run_usb_devctl.bat
│       │   smartpos_usb_service_v14.py
│       │   trace_wrappers_v2.py
│       │   usb_agent_autotests.py
│       │   usb_agent_core.py
│       │   usb_agent_smoketests.py
│       │   usb_devctl_cli.py
│       │
│       ├───db
│       │       .gitkeep
│       │       smartpos_usb.db.bak_20251003_195540
│       │
│       ├───helpers
│       │       __init__.py
│       │
│       ├───logs
│       │       .gitkeep
│       │
│       └───__pycache__
│               usb_devctl_cli.cpython-311.pyc
│
├───tests
│   │   test_cli_export_smoke.py
│   │   test_config_and_hot_reload.py
│   │   test_export_zip_mask.py
│   │   test_sqlite_retention.py
│   │   test_usb_agent_autotests.py
│   │
│   ├───.pytest_cache
│   │   │   .gitignore
│   │   │   CACHEDIR.TAG
│   │   │   README.md
│   │   │
│   │   └───v
│   │       └───cache
│   │               lastfailed
│   │               nodeids
│   │
│   └───__pycache__
│           test_cli_export_smoke.cpython-311-pytest-8.4.2.pyc
│           test_config_and_hot_reload.cpython-311-pytest-8.4.2.pyc
│           test_export_zip_mask.cpython-311-pytest-8.4.2.pyc
│           test_sqlite_retention.cpython-311-pytest-8.4.2.pyc
│           test_usb_agent_autotests.cpython-311-pytest-8.4.2.pyc
│
└───tools
    │   checklist_install_smoke.ps1
    │   install_watchdog.ps1
    │   make_release_zip.ps1
    │   Test-InnoIss.ps1
    │   uninstall_watchdog.ps1
    │   watchdog_core.ps1
    │
    └───ux
            config.json
            service_name_map.json
            SmartPOS-USB-UX.ps1
tchdog.ps1
└── structure.md
