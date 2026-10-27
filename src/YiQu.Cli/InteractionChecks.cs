using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using YiQu;

// Exercises actual WPF click handlers with in-memory clipboard data, a loopback service,
// and real speech synthesis played silently. Never reads clipboard contents, saves history or settings.
internal static class InteractionChecks
{
    const BindingFlags Private = BindingFlags.Instance | BindingFlags.NonPublic;
    static T Field<T>(object obj, string name) => (T)obj.GetType().GetField(name, Private)!.GetValue(obj)!;
    static void Call(object obj, string name, params object[] args) => obj.GetType().GetMethod(name, Private)!.Invoke(obj, args);
    static void Check(bool condition, string label) { if (!condition) throw new Exception(label); Console.WriteLine("PASS " + label); }
    static void Click(Button button) => button.RaiseEvent(new RoutedEventArgs(Button.ClickEvent));
    static IEnumerable<T> Find<T>(DependencyObject root) where T : DependencyObject
    {
        if (root is T match) yield return match;
        foreach (var child in LogicalTreeHelper.GetChildren(root).OfType<DependencyObject>())
            foreach (var item in Find<T>(child)) yield return item;
    }
    static async Task Until(Func<bool> predicate)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        while (!predicate()) await Task.Delay(30, timeout.Token);
    }
    static Dictionary<string,string> UserDataHashes() => new[] { "settings.json", "history.json" }
        .ToDictionary(n => n, n => { var p = Path.Combine(SettingsStore.DirectoryPath, n); return File.Exists(p) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(p))) : "absent"; });

    public static int Run()
    {
        int exit = 1;
        var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
        Theme.Initialize(false); Theme.Attach(app.Resources);
        app.Dispatcher.BeginInvoke(async () => {
            try { await Verify(); exit = 0; }
            catch (Exception ex) { Console.Error.WriteLine(ex); }
            finally { Speech.Stop(); app.Shutdown(); }
        });
        app.Run(); return exit;
    }
    // Keyboard focus needs a real window, so this one is shown off-screen.
    static async Task CheckSourceEditing()
    {
        var window = new MainWindow(new AppSettings { SaveHistory = false, MarkdownSource = true }, desktopIntegration: false) { Left = -4000, Top = 0, ShowActivated = true };
        window.SaveSettings = _ => { };
        try {
            window.Show(); window.Activate();
            var input = Field<TextBox>(window, "input");
            var preview = Field<RichTextBox>(window, "sourceView");
            const string source = "alpha **beta** gamma\n\nSee [docs](https://example.com/docs) here";
            window.SetVerificationContent(source, new List<TranslationResult> { new("A", "译文") }, "");
            await Task.Delay(100);
            Check(preview.IsVisible && !input.IsVisible, "source with text shows the preview when Markdown is on");

            Point PointAt(string word)
            {
                var run = Find<System.Windows.Documents.Run>(preview.Document).First(r => r.Text.Contains(word));
                var rect = run.ContentStart.GetPositionAtOffset(run.Text.IndexOf(word))!.GetCharacterRect(System.Windows.Documents.LogicalDirection.Forward);
                return preview.TranslatePoint(new Point(rect.X + 1, rect.Y + rect.Height / 2), preview);
            }
            Check(!window.EditSourceAt(PointAt("docs")) && preview.IsVisible, "clicking a link in the preview does not open the editor");
            Check(window.EditSourceAt(PointAt("gamma")) && input.IsVisible && input.IsKeyboardFocused && input.CaretIndex == source.IndexOf("gamma"),
                "clicking the preview opens the editor with the caret at the clicked word");
            System.Windows.Documents.EditingCommands.Backspace.Execute(null, input);
            Check(input.Text.StartsWith("alpha **beta**gamma"), "text can be deleted in the middle after clicking the preview");
            var card = Find<TextBox>(Field<StackPanel>(window, "cards")).First();
            card.Focus();
            await Task.Delay(50);
            Check(preview.IsVisible && !input.IsVisible && new System.Windows.Documents.TextRange(preview.Document.ContentStart, preview.Document.ContentEnd).Text.Contains("betagamma"),
                "leaving the editor renders the edited source again");
        } finally { window.Close(); }
    }

    static async Task Verify()
    {
        var before = UserDataHashes();
        using var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start();
        int port = ((IPEndPoint)listener.LocalEndpoint).Port;
        var settings = new AppSettings { SaveHistory = false, Services = new() {
            new() { Name = "本地测试", Endpoint = $"http://127.0.0.1:{port}/v1/chat/completions", Model = "fixture" }
        }, Ocr = new() { Provider = "windows", Language = "en-US" } };
        var window = new MainWindow(settings);
        var input = Field<TextBox>(window, "input");
        var cards = Field<StackPanel>(window, "cards");
        var clear = Field<Button>(window, "clear");
        var clipboardButton = Find<Button>(window).Single(b => Equals(b.ToolTip, "翻译剪贴板文本或图片 (Alt+C)"));
        IDataObject clipboard = new DataObject(DataFormats.UnicodeText, "Clipboard translation fixture");
        window.ReadClipboard = () => clipboard;

        async Task<string> Respond()
        {
            using var client = await listener.AcceptTcpClientAsync().WaitAsync(TimeSpan.FromSeconds(15));
            using var stream = client.GetStream();
            var header = new List<byte>(); var one = new byte[1];
            while (header.Count < 65536) {
                if (await stream.ReadAsync(one) == 0) throw new IOException("Incomplete request");
                header.Add(one[0]);
                if (header.Count >= 4 && Encoding.ASCII.GetString(header.TakeLast(4).ToArray()) == "\r\n\r\n") break;
            }
            int size = int.Parse(Encoding.ASCII.GetString(header.ToArray()).Split("\r\n").Single(x => x.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)).Split(':')[1]);
            var body = new byte[size]; await stream.ReadExactlyAsync(body);
            using var json = JsonDocument.Parse(body);
            string source = json.RootElement.GetProperty("messages")[1].GetProperty("content").GetString()!;
            var result = Encoding.UTF8.GetBytes("{\"choices\":[{\"message\":{\"content\":\"本地测试译文\"}}]}");
            await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {result.Length}\r\nConnection: close\r\n\r\n"));
            await stream.WriteAsync(result); return source;
        }
        var request = Respond(); Click(clipboardButton);
        Check(!clear.IsEnabled, "clear disabled while translation is pending");
        Call(window, "ClearPanel");
        Check(input.Text == "Clipboard translation fixture", "busy clear cannot erase an active request");
        Check(await request == "Clipboard translation fixture", "clipboard click submits fresh text without a second click");
        await Until(() => !Field<bool>(window, "busy"));
        Check(Find<TextBox>(cards).Any(b => b.Text == "本地测试译文"), "clipboard translation displays the response");
        clipboard = new DataObject(); input.Text = "previous source"; Click(clipboardButton);
        Check(input.Text == "" && !listener.Pending(), "empty clipboard never resubmits previous input");

        clipboard = new DataObject(DataFormats.Bitmap, TestImages.Text());
        request = Respond(); Click(clipboardButton);
        Check((await request).Contains("Windows OCR", StringComparison.OrdinalIgnoreCase), "clipboard image is recognized then translated");
        await Until(() => !Field<bool>(window, "busy"));
        // Real synthesis and winmm playback with zeroed samples.
        Speech.Silent = true;
        string longText = string.Join(" ", Enumerable.Repeat("This is a muted speech playback test.", 20));
        window.SetVerificationContent("sample", new List<TranslationResult> { new("A", longText), new("B", longText) }, "");
        var speakers = Find<Button>(cards).Where(b => Equals(b.ToolTip, "朗读")).ToArray();
        Click(speakers[0]); Check(Equals(speakers[0].ToolTip, "停止朗读"), "first click shows stop immediately");
        await Until(() => !Speech.Finished);
        Check(Equals(speakers[0].ToolTip, "停止朗读"), "synthesized speech starts playing");
        var timer = System.Diagnostics.Stopwatch.StartNew();
        Click(speakers[0]);
        Check(timer.ElapsedMilliseconds < 500 && Speech.Finished && Equals(speakers[0].ToolTip, "朗读"), $"second click stops playback without blocking ({timer.ElapsedMilliseconds} ms)");
        Click(speakers[0]); Click(speakers[0]); await Task.Delay(2500);
        Check(Speech.Finished && Equals(speakers[0].ToolTip, "朗读"), "stopping during synthesis prevents playback");
        Click(speakers[0]); Click(speakers[1]);
        Check(Equals(speakers[0].ToolTip, "朗读") && Equals(speakers[1].ToolTip, "停止朗读"), "switching result stops previous playback and moves stop state");
        await Until(() => !Speech.Finished);
        Click(clear);
        Check(Speech.Finished && input.Text == "" && cards.Children.Count == 0 && Field<FrameworkElement>(window, "emptyState").Visibility == Visibility.Visible && Field<TextBlock>(window, "status").Text == "", "clear returns to initial panel and stops sound");
        Click(clear); Check(Speech.Finished, "clearing empty panel is harmless");
        window.SetVerificationContent("sample", new List<TranslationResult> { new("A", "Done.") }, "");
        var shortSpeaker = Find<Button>(cards).Single(b => Equals(b.ToolTip, "朗读"));
        Click(shortSpeaker); await Until(() => !Speech.Finished); await Until(() => Equals(shortSpeaker.ToolTip, "朗读"));
        Check(Speech.Finished, "natural speech completion restores button");
        Click(shortSpeaker); Check(Equals(shortSpeaker.ToolTip, "停止朗读"), "completed speech can play again");
        Click(clear);

        // Markdown toggles: one shared state for all result cards, saved through the injected setter only.
        AppSettings? saved = null;
        window.SaveSettings = s => saved = s;
        window.SetVerificationContent("**source**", new List<TranslationResult> { new("A", "**粗体** 与 `code`"), new("B", "| a | b |\n| - | - |\n| 1 | 2 |") }, "");
        var toggles = Find<ToggleButton>(cards).Where(t => Equals(t.ToolTip, "Markdown 渲染")).ToArray();
        Check(toggles.Length == 2 && toggles.All(t => t.IsChecked == false) && !Find<RichTextBox>(cards).Any(), "results start as plain text");
        toggles[0].IsChecked = true; toggles[0].RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        var views = Find<RichTextBox>(cards).ToArray();
        Check(saved?.MarkdownResults == true && toggles[1].IsChecked == true && views.Length == 2 && views.All(v => v.Visibility == Visibility.Visible), "one toggle renders every result and saves the state");
        Check(views[0].Document.Blocks.OfType<System.Windows.Documents.Paragraph>().Single().Inlines.OfType<System.Windows.Documents.Bold>().Any(), "bold markup renders as bold");
        Check(views[1].Document.Blocks.OfType<System.Windows.Documents.Table>().Single().RowGroups[0].Rows.Count == 2, "pipe table renders as a table");
        Check(Find<TextBox>(cards).All(t => t.Visibility == Visibility.Collapsed), "plain text is hidden while rendered");
        toggles[1].IsChecked = false; toggles[1].RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        Check(saved?.MarkdownResults == false && toggles[0].IsChecked == false && Find<TextBox>(cards).Any(t => t.Text == "**粗体** 与 `code`" && t.Visibility == Visibility.Visible), "turning it off restores the original text");
        var sourceToggle = Field<ToggleButton>(window, "sourceMarkdown");
        var sourceView = Field<RichTextBox>(window, "sourceView");
        sourceToggle.IsChecked = true; sourceToggle.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        Check(saved?.MarkdownSource == true && sourceView.Visibility == Visibility.Visible && input.Visibility == Visibility.Collapsed && input.Text == "**source**", "source toggle renders the source without changing it");
        Click(clear);
        Check(input.Visibility == Visibility.Visible && sourceView.Visibility == Visibility.Collapsed, "empty source shows the editor");
        sourceToggle.IsChecked = false; sourceToggle.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        await CheckSourceEditing();
        var preferences = new SettingsWindow(new AppSettings());
        preferences.SelectVerificationTab(1);
        var provider = Find<ComboBox>(preferences).Single(b => b.SelectedValuePath == "Tag");
        Check(Equals(provider.SelectedValue, "windows"), "new configuration defaults to Windows OCR");
        Click(Find<Button>(preferences).Single(b => Equals(b.Content, "设置 RapidOCR")));
        Check(Equals(provider.SelectedValue, "rapidocr"), "Windows OCR page opens RapidOCR setup");
        if (RapidOcrRuntime.InstalledPython() != null) {
            var install = Find<Button>(preferences).Single(b => Equals(b.Content, "检查组件"));
            var save = Field<Button>(preferences, "save");
            Click(install);
            Check(!save.IsEnabled && !provider.IsEnabled, "component operation prevents premature save or engine switch");
            await Until(() => install.IsEnabled);
            Check(Find<TextBlock>(preferences).Any(t => t.Text == "组件已就绪，保存后启用") && save.IsEnabled,
                "settings component button completes real verification and restores controls");
            Check(preferences.Result == null, "component installation does not save settings automatically");
        }
        Check(before.OrderBy(p => p.Key).SequenceEqual(UserDataHashes().OrderBy(p => p.Key)), "settings and history remain byte-for-byte unchanged");
    }
}
