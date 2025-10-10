#!/usr/bin/env python3
"""
Запуск всех тестов SmartPOS POS Protect

Запускает все доступные тесты и выводит сводку результатов.

Использование:
    python run_tests.py [--verbose]

Автор: SmartPOS POS Protect Team
Версия: 1.0
"""

import sys
import subprocess
import pathlib
import argparse

def run_test_file(test_file, verbose=False):
    """Запустить один тестовый файл."""
    test_path = pathlib.Path(__file__).parent / "tests" / test_file
    
    if not test_path.exists():
        print(f"ERROR: Test file not found: {test_file}")
        return False
    
    print(f"\nRunning {test_file}...")
    print("-" * 50)
    
    try:
        result = subprocess.run([sys.executable, str(test_path)], 
                              capture_output=True, text=True, timeout=120)
        
        if result.returncode == 0:
            print(f"OK {test_file} PASSED")
            if verbose and result.stdout:
                print("Output:")
                print(result.stdout)
            return True
        else:
            print(f"FAILED {test_file}")
            print("Error output:")
            print(result.stderr)
            if verbose and result.stdout:
                print("Standard output:")
                print(result.stdout)
            return False
            
    except subprocess.TimeoutExpired:
        print(f"TIMEOUT {test_file} (120s)")
        return False
    except Exception as e:
        print(f"ERROR {test_file}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Run SmartPOS POS Protect tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Список тестовых файлов
    test_files = [
        "test_rules_simple_ascii.py",
        "test_actions_simple_ascii.py", 
        "test_pipeline_smoke_ascii.py"
    ]
    
    print("Starting SmartPOS POS Protect Test Suite")
    print("=" * 60)
    
    passed = 0
    total = len(test_files)
    
    for test_file in test_files:
        if run_test_file(test_file, args.verbose):
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed}/{total} passed")
    
    if passed == total:
        print("SUCCESS: All tests passed!")
        sys.exit(0)
    else:
        print("ERROR: Some tests failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
