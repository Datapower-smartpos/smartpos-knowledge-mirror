// SmartPOS.UsbTray — WinForms tray app (C#)
// Author: Разработчик суперпрограмм
// Сборка: dotnet build -c Release; dotnet publish -c Release
// Требования: .NET 6+; использует SMARTPOS_USB_APIKEY для POST

using System;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace SmartPOS.UsbTray
{
    internal static class Program
    {
        [STAThread]
        static void Main()
        {
            ApplicationConfiguration.Initialize();
            using var app = new TrayApp();
            Application.Run();
        }
    }

    public class TrayApp : IDisposable
    {
        private readonly NotifyIcon _tray;
        private readonly Timer _timer;
        private readonly HttpClient _http;
        private readonly string _baseUrl = "http://127.0.0.1:8765";
        private readonly string? _apiKey = Environment.GetEnvironmentVariable("SMARTPOS_USB_APIKEY");

        public TrayApp()
        {
            _http = new HttpClient();
            _tray = new NotifyIcon { Visible = true, Text = "SmartPOS USB", Icon = SystemIcons.Information };
            var menu = new ContextMenuStrip();
            var miStatus = menu.Items.Add("Статус"); miStatus.Click += async (_, __) => await ShowStatusAsync();
            var miPreflight = menu.Items.Add("Проверить (Preflight)"); miPreflight.Click += async (_, __) => await PreflightAsync();
            var miRecover = menu.Items.Add("Восстановить выбранное..."); miRecover.Click += async (_, __) => await RecoverAsync();
            var miExport = menu.Items.Add("Сохранить отчёт (ZIP)"); miExport.Click += async (_, __) => await ExportAsync();
            menu.Items.Add("-");
            var miExit = menu.Items.Add("Выход"); miExit.Click += (_, __) => { _tray.Visible = false; Application.Exit(); };
            _tray.ContextMenuStrip = menu;

            _timer = new Timer { Interval = 4000 };
            _timer.Tick += async (_, __) => await RefreshIconAsync();
            _timer.Start();
        }

        private async Task RefreshIconAsync()
        {
            var lvl = await GetOverallAsync();
            _tray.Icon = lvl switch
            {
                "red" => SystemIcons.Error,
                "yellow" => SystemIcons.Warning,
                _ => SystemIcons.Information
            };
        }

        private async Task<JsonDocument?> GetStatusAsync()
        {
            try
            {
                var s = await _http.GetStringAsync($"{_baseUrl}/api/status");
                return JsonDocument.Parse(s);
            }
            catch { return null; }
        }

        private static string OverallFromStatus(JsonDocument? doc)
        {
            if (doc == null) return "red";
            try
            {
                var root = doc.RootElement.GetProperty("status");
                var anyFailed = root.EnumerateObject().Any(p => p.Value.GetProperty("state").GetString() == "FAILED");
                if (anyFailed) return "red";
                var anyDegraded = root.EnumerateObject().Any(p =>
                    new[] { "DEGRADED", "RECOVERING" }.Contains(p.Value.GetProperty("state").GetString()));
                return anyDegraded ? "yellow" : "green";
            }
            catch { return "red"; }
        }

        private async Task<string> GetOverallAsync()
        {
            using var s = await GetStatusAsync();
            return OverallFromStatus(s);
        }

        private void Balloon(string title, string text, ToolTipIcon icon = ToolTipIcon.Info)
        {
            _tray.BalloonTipTitle = title;
            _tray.BalloonTipText = text;
            _tray.BalloonTipIcon = icon;
            _tray.ShowBalloonTip(3000);
        }

        private HttpRequestMessage Post(string path)
        {
            var req = new HttpRequestMessage(HttpMethod.Post, _baseUrl + path);
            if (!string.IsNullOrWhiteSpace(_apiKey)) req.Headers.Add("X-API-Key", _apiKey);
            req.Content = new StringContent("{}", Encoding.UTF8, "application/json");
            return req;
        }

        private async Task ShowStatusAsync()
        {
            using var s = await GetStatusAsync();
            if (s == null) { Balloon("SmartPOS USB", "Служба недоступна", ToolTipIcon.Error); return; }
            var sb = new StringBuilder();
            foreach (var dev in s.RootElement.GetProperty("status").EnumerateObject())
            {
                var rec = dev.Value.GetProperty("record");
                var friendly = rec.GetProperty("friendly").GetString();
                var state = dev.Value.GetProperty("state").GetString();
                var com = rec.TryGetProperty("com_port", out var cp) ? cp.GetString() : null;
                sb.AppendLine($"{friendly} — {state} (COM={com})");
            }
            Balloon("Статус устройств", sb.ToString());
        }

        private async Task PreflightAsync()
        {
            try
            {
                using var req = Post("/api/preflight");
                var resp = await _http.SendAsync(req);
                resp.EnsureSuccessStatusCode();
                var s = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
                var lvl = OverallFromStatus(s);
                Balloon("Preflight", "Готовность: " + lvl);
            }
            catch { Balloon("Preflight", "Ошибка запроса", ToolTipIcon.Error); }
        }

        private async Task RecoverAsync()
        {
            using var s = await GetStatusAsync();
            if (s == null) { Balloon("Восстановить", "Служба недоступна", ToolTipIcon.Error); return; }
            var root = s.RootElement.GetProperty("status");
            var items = root.EnumerateObject().Select(p => new
            {
                Id = p.Name,
                Friendly = p.Value.GetProperty("record").GetProperty("friendly").GetString()
            }).ToList();
            if (items.Count == 0) { Balloon("Восстановить", "Нет устройств", ToolTipIcon.Warning); return; }
            using var dlg = new SelectDeviceForm(items.Select(i => ($"{i.Friendly} [{i.Id}]", i.Id)).ToArray());
            if (dlg.ShowDialog() == DialogResult.OK)
            {
                try
                {
                    using var req = Post($"/api/action/device/{Uri.EscapeDataString(dlg.SelectedId)}/recycle");
                    var resp = await _http.SendAsync(req);
                    if (resp.IsSuccessStatusCode) Balloon("Восстановление", "Команда отправлена");
                    else Balloon("Восстановление", "Ошибка запроса", ToolTipIcon.Error);
                }
                catch { Balloon("Восстановление", "Ошибка запроса", ToolTipIcon.Error); }
            }
        }

        private async Task ExportAsync()
        {
            try
            {
                using var req = Post("/api/export?mask=db,logs");
                var resp = await _http.SendAsync(req);
                resp.EnsureSuccessStatusCode();
                var bytes = await resp.Content.ReadAsByteArrayAsync();
                var downloads = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
                var path = Path.Combine(downloads, "Downloads", "smartpos_usb_export.zip");
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                await File.WriteAllBytesAsync(path, bytes);
                Balloon("Экспорт", "Сохранено: " + path, ToolTipIcon.Info);
            }
            catch { Balloon("Экспорт", "Ошибка экспорта", ToolTipIcon.Error); }
        }

        public void Dispose()
        {
            _timer.Dispose();
            _tray.Dispose();
            _http.Dispose();
        }
    }

    public class SelectDeviceForm : Form
    {
        private readonly ComboBox _combo = new ComboBox();
        private readonly Button _ok = new Button();
        private readonly (string Text, string Id)[] _items;
        public string SelectedId { get; private set; } = string.Empty;

        public SelectDeviceForm((string Text, string Id)[] items)
        {
            _items = items;
            Text = "Восстановить устройство";
            Width = 480; Height = 180; StartPosition = FormStartPosition.CenterScreen;
            _combo.Left = 12; _combo.Top = 12; _combo.Width = 440; _combo.DropDownStyle = ComboBoxStyle.DropDownList;
            foreach (var it in _items) _combo.Items.Add(it.Text);
            _ok.Text = "Восстановить (recycle)"; _ok.Left = 12; _ok.Top = 60; _ok.Width = 200;
            _ok.Click += (_, __) => { if (_combo.SelectedIndex >= 0) { SelectedId = _items[_combo.SelectedIndex].Id; DialogResult = DialogResult.OK; } };
            Controls.Add(_combo); Controls.Add(_ok);
            TopMost = true;
        }
    }
}
