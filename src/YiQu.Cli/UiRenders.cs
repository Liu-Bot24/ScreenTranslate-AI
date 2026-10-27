using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using YiQu;

/// <summary>
/// Renders the real window content with sample data to PNG files, in light and dark themes.
/// Never shows a window, registers hotkeys, touches the clipboard, makes network requests or reads saved history.
/// </summary>
internal static class UiRenders
{
    public static void Render(string directory)
    {
        RenderOptions.ProcessRenderMode = System.Windows.Interop.RenderMode.SoftwareOnly;
        Directory.CreateDirectory(directory);
        var settings = new AppSettings {
            SaveHistory = false, SecondaryLanguage = "Tiếng Việt",
            Services = new List<TranslationService> {
                new() { Name = "翻译服务 A（示例）", Endpoint = "https://example.com/v1/chat/completions", Model = "example-model", Enabled = true },
                new() { Name = "翻译服务 B（示例）", Endpoint = "https://example.org/v1/chat/completions", Model = "example-model", Enabled = true }
            },
            Ocr = new OcrSettings { Provider = "rapidocr" }
        };
        const string source = "Good tools should make everyday work easier.\nSelect a sentence, press a shortcut, and keep your focus.";
        var results = new List<TranslationResult> {
            new("翻译服务 A（示例）", "好用的工具应该让日常工作更轻松。\n选中一句话，按下快捷键，继续专注当前任务。"),
            new("翻译服务 B（示例）", "好的工具能简化日常工作。\n只需选中文字、按下快捷键，就能在不中断思路的情况下获得翻译。")
        };
        var entries = new List<HistoryEntry> {
            new() { Time = new DateTimeOffset(2026, 10, 21, 14, 30, 0, TimeSpan.FromHours(8)), Source = source, Target = "简体中文", Results = results, Favorite = true },
            new() { Time = new DateTimeOffset(2026, 10, 21, 14, 10, 0, TimeSpan.FromHours(8)), Source = "这是界面示例，不会读取或修改历史记录。", Target = "English", Results = new() { new("翻译服务 A（示例）", "This is a UI sample. It does not read or modify history.") } }
        };
        var markdownSettings = JsonSerializer.Deserialize<AppSettings>(JsonSerializer.Serialize(settings))!;
        markdownSettings.MarkdownSource = markdownSettings.MarkdownResults = true;
        const string markdownSource = "## Release notes\n- **Faster** startup, *smaller* package\n- Press `Ctrl+Enter` to translate";
        var markdownResults = new List<TranslationResult> {
            new("翻译服务 A（示例）", "## 更新说明\n\n1. **启动更快**，*安装包更小*\n2. 按 `Ctrl+Enter` 翻译，等待 10~20 秒\n   - 嵌套项 ~~已删除~~\n\n> 引用：保持专注。\n\n| 快捷键 | 功能 |\n| --- | :---: |\n| Alt+Q | 划词翻译 |\n| Alt+W | 截图翻译 |\n\n```\ncode block 代码\n```\n\n详见 [文档](https://example.com/docs)。"),
            new("翻译服务 B（示例）", "第一行\n第二行（单个换行保留）")
        };
        var markdownEntries = new List<HistoryEntry> { new() { Time = entries[0].Time, Source = markdownSource, Target = "简体中文", Results = markdownResults } };

        void Save(Window window, string name, int width, int height) => RenderContent(window, Path.Combine(directory, name), width, height);
        MainWindow Home(AppSettings s, string text, IReadOnlyList<TranslationResult> items, bool busy = false)
        {
            var window = new MainWindow(s);
            window.SetVerificationContent(text, items, "", busy);
            return window;
        }
        SettingsWindow Settings(AppSettings s, int tab)
        {
            var window = new SettingsWindow(s);
            window.SelectVerificationTab(tab);
            return window;
        }

        foreach (var dark in new[] { false, true }) {
            Theme.Initialize(dark);
            string suffix = dark ? "-dark" : "";
            Save(Home(settings, source, results), $"main-results{suffix}.png", 820, 660);
            Save(Home(markdownSettings, markdownSource, markdownResults), $"main-markdown{suffix}.png", 820, 1000);
            Save(Home(settings, "", Array.Empty<TranslationResult>()), $"main-empty{suffix}.png", 820, 660);
            Save(new HistoryWindow(_ => { }, entries), $"history{suffix}.png", 920, 620);
            Save(new HistoryWindow(_ => { }, markdownEntries, markdown: true), $"history-markdown{suffix}.png", 920, 900);
            Save(Settings(settings, 0), $"settings-services{suffix}.png", 860, 720);
            Save(Settings(settings, 1), $"settings-ocr{suffix}.png", 860, 720);
            Save(Settings(new AppSettings(), 1), $"settings-windows-ocr{suffix}.png", 860, 720);
        }
        Theme.Initialize(false);
        Save(Home(settings, source, results), "main-narrow.png", 520, 660);
        Save(Home(settings, source, Array.Empty<TranslationResult>(), busy: true), "main-busy.png", 820, 660);
        Save(Home(settings, "Example text for failure rendering.", new[] { new TranslationResult("失败状态示例", "", "无法连接服务，请检查网络和接口地址") }), "main-error.png", 820, 660);
        Save(Settings(settings, 2), "settings-general.png", 860, 720);
        Save(new HistoryWindow(_ => { }, new List<HistoryEntry>()), "history-empty.png", 920, 620);
    }

    static void RenderContent(Window window, string file, int width, int height)
    {
        if (window.Content is not FrameworkElement content) throw new InvalidOperationException("窗口没有可渲染内容");
        // Render detached content so Window.SourceInitialized cannot run.
        window.Content = null;
        // ContentControl's default template does not paint its Background, so a Border reproduces it.
        var host = new Border {
            Child = content, Width = width, Height = height,
            Background = window.Background ?? Brushes.White,
            UseLayoutRounding = true, SnapsToDevicePixels = true
        };
        TextElement.SetFontFamily(host, window.FontFamily);
        TextElement.SetFontSize(host, window.FontSize);
        TextElement.SetForeground(host, window.Foreground);
        host.Measure(new Size(width, height));
        host.Arrange(new Rect(0, 0, width, height));
        host.UpdateLayout();
        // Flush binding and template work before recording the detached visual tree.
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.Loaded);
        host.UpdateLayout();
        Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.Render);
        host.UpdateLayout();
        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
        var background = new DrawingVisual();
        using (var drawing = background.RenderOpen()) drawing.DrawRectangle(window.Background ?? Brushes.White, null, new Rect(0, 0, width, height));
        bitmap.Render(background);
        bitmap.Render(host);
        var pixels = new byte[width * height * 4];
        bitmap.CopyPixels(pixels, width * 4, 0);
        // A transparent pixel means some area was left unpainted. Antialiased edges can round alpha to 254.
        for (int alpha = 3; alpha < pixels.Length; alpha += 4)
            if (pixels[alpha] < 250) throw new InvalidOperationException($"{Path.GetFileName(file)}: unpainted pixel {(alpha - 3) / 4}");
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var stream = File.Create(file); encoder.Save(stream);
        host.Child = null;
    }
}
