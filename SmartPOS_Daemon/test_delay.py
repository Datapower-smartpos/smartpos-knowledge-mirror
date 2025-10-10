import urllib.request
import urllib.parse
import json
import time
import win32print

def test_with_delay():
    print("=== Тест с задержкой отмены ===")
    
    # Создаем залипание
    print("\n1. Создание залипания...")
    try:
        data = json.dumps({'kind': 'sticky_queue'}).encode('utf-8')
        req = urllib.request.Request('http://127.0.0.1:7078/faults/create', 
                                   data=data, 
                                   headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        print("Результат:", result)
    except Exception as e:
        print("Ошибка:", e)
        return
    
    # Проверяем очередь сразу
    print("\n2. Проверка очереди сразу после создания...")
    try:
        printer_name = win32print.GetDefaultPrinter()
        h = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(h, 0, 999, 1)
            print(f"Найдено джобов: {len(jobs)}")
            for job in jobs:
                print(f"  JobId: {job['JobId']}, Document: {job['Document']}, Status: {job['Status']}")
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:
        print(f"Ошибка проверки очереди: {e}")
    
    # Ждем 3 секунды
    print("\n3. Ожидание 3 секунды...")
    time.sleep(3)
    
    # Проверяем очередь снова
    print("\n4. Проверка очереди через 3 секунды...")
    try:
        printer_name = win32print.GetDefaultPrinter()
        h = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(h, 0, 999, 1)
            print(f"Найдено джобов: {len(jobs)}")
            for job in jobs:
                print(f"  JobId: {job['JobId']}, Document: {job['Document']}, Status: {job['Status']}")
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:
        print(f"Ошибка проверки очереди: {e}")
    
    # Запускаем PR0018
    print("\n5. Запуск PR0018...")
    start_time = time.time()
    try:
        data = json.dumps({'ticket_id': 'DBG-PR0018-DELAY', 
                          'problem_code': 'PR0018', 
                          'device': {'type': 'receipt_printer'}}).encode('utf-8')
        req = urllib.request.Request('http://127.0.0.1:7078/action/run', 
                                   data=data, 
                                   headers={'Content-Type': 'application/json'})
        response = urllib.request.urlopen(req)
        result = json.loads(response.read().decode('utf-8'))
        end_time = time.time()
        print(f"Результат (время выполнения: {end_time - start_time:.2f}с):", result)
    except Exception as e:
        print("Ошибка:", e)
    
    # Проверяем очередь после PR0018
    print("\n6. Проверка очереди после PR0018...")
    try:
        printer_name = win32print.GetDefaultPrinter()
        h = win32print.OpenPrinter(printer_name)
        try:
            jobs = win32print.EnumJobs(h, 0, 999, 1)
            print(f"Найдено джобов: {len(jobs)}")
            for job in jobs:
                print(f"  JobId: {job['JobId']}, Document: {job['Document']}, Status: {job['Status']}")
        finally:
            win32print.ClosePrinter(h)
    except Exception as e:
        print(f"Ошибка проверки очереди: {e}")

if __name__ == "__main__":
    test_with_delay()
