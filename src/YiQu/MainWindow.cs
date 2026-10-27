using System;
using System.Collections.Generic;
using System.Linq;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Documents;
using System.Windows.Input;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Forms = System.Windows.Forms;

namespace YiQu;

public sealed class MainWindow : ShellWindow
{
    AppSettings settings;
    readonly TextBox input = new() { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MinHeight = 112, MaxHeight = 260, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Tag = "输入要翻译的文本" };
    readonly ComboBox target = new() { MinWidth = 118, VerticalAlignment = VerticalAlignment.Center };
    readonly StackPanel cards = new();
    readonly FrameworkElement emptyState;
    readonly TextBlock status = Theme.Text("", 12, "TextFaint");
    readonly ProgressBar progress = new() { Visibility = Visibility.Collapsed, VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(14, 0, 14, 0) };
    readonly List<TextBlock> toolLabels = new();
    readonly Button translate;
    readonly Button cancel;
    readonly Button clear;
    readonly RichTextBox sourceView = MarkdownView.Create(16);
    readonly ToggleButton sourceMarkdown;
    readonly List<(ToggleButton Toggle, MarkdownText Body)> resultViews = new();
    readonly DispatcherTimer speechTimer = new() { Interval = TimeSpan.FromMilliseconds(150) };
    Button? speakingButton;
    CancellationTokenSource? speechCancel;
    internal Func<IDataObject?> ReadClipboard { get; set; } = Clipboard.GetDataObject;
    internal Action<AppSettings> SaveSettings { get; set; } = SettingsStore.Save;
    CancellationTokenSource? active;
    CancellationTokenSource? warmup;
    HotkeyManager? hotkeys;
    Forms.NotifyIcon? tray;
    bool quitting;
    bool busy;

    public MainWindow(AppSettings settings) : this(settings, true) { }
    internal MainWindow(AppSettings settings, bool desktopIntegration) : base("译取", dialog: false)
    {
        this.settings = settings;
        Title = "译取";
        Width = 820; Height = 660; MinWidth = 520; MinHeight = 460;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;

        var pin = new ToggleButton { Content = Theme.IconPin, ToolTip = "窗口置顶", Margin = new Thickness(2, 0, 2, 0) }.Styled("IconToggle");
        pin.Checked += (_, _) => { Topmost = true; pin.Content = Theme.IconPinned; pin.ToolTip = "取消置顶"; };
        pin.Unchecked += (_, _) => { Topmost = false; pin.Content = Theme.IconPin; pin.ToolTip = "窗口置顶"; };
        AddTitleAction(pin);
        AddTitleAction(Theme.IconButton(Theme.IconHistory, "历史与收藏", (_, _) => ShowHistory()));
        clear = Theme.IconButton(Theme.IconClear, "清除当前面板", (_, _) => {
            try { ClearPanel(); } catch (Exception ex) { SetStatus("清除失败：" + ex.Message); }
        });
        AddTitleAction(clear);
        AddTitleAction(Theme.IconButton(Theme.IconSettings, "设置", (_, _) => ShowSettings()));
        speechTimer.Tick += (_, _) => {
            try { if (Speech.Finished) StopSpeech(); }
            catch (Exception ex) { speechTimer.Stop(); SetStatus("无法获取朗读状态：" + ex.Message); }
        };

        var root = new DockPanel { Margin = new Thickness(20, 6, 20, 20) };
        Body = root;

        // Composer card: source header, input (or its rendered Markdown), then tools + target language + translate.
        input.Styled("Composer"); input.Padding = new Thickness(21, 4, 21, 6);
        var composerGrid = new Grid();
        for (int i = 0; i < 3; i++) composerGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        sourceMarkdown = Theme.MarkdownToggle(settings.MarkdownSource);
        sourceMarkdown.Click += (_, _) => { settings.MarkdownSource = sourceMarkdown.IsChecked == true; Persist(); UpdateSourceView(); };
        Button? sourceCopy = null, sourceSpeak = null;
        sourceCopy = Theme.IconButton(Theme.IconCopy, "复制", (_, _) => CopyText(input.Text, sourceCopy!));
        sourceSpeak = Theme.IconButton(Theme.IconSpeak, "朗读", (_, _) => ToggleSpeech(sourceSpeak!, settings.MarkdownSource ? MarkdownView.PlainText(input.Text) : input.Text));
        var sourceHeader = Header(Theme.Dot("TextFaint"), "原文", "TextMuted", sourceMarkdown, sourceCopy, sourceSpeak);
        sourceHeader.Margin = new Thickness(18, 12, 10, 0);
        composerGrid.Children.Add(sourceHeader);
        var sourceArea = new Grid();
        sourceArea.Children.Add(input);
        sourceView.Margin = new Thickness(18, 4, 18, 6); sourceView.MinHeight = 102; sourceView.MaxHeight = 250;
        sourceView.VerticalScrollBarVisibility = ScrollBarVisibility.Auto; sourceView.Visibility = Visibility.Collapsed;
        sourceArea.Children.Add(sourceView);
        // With Markdown on, the source shows the preview except while it is edited: clicking the preview
        // opens the editor at that spot, and moving focus elsewhere in the window renders it again.
        sourceView.PreviewMouseLeftButtonDown += (_, e) => { if (EditSourceAt(e.GetPosition(sourceView))) e.Handled = true; };
        input.LostKeyboardFocus += (_, e) => { if (e.NewFocus != null) UpdateSourceView(); }; // Switching apps keeps the editor.
        Grid.SetRow(sourceArea, 1); composerGrid.Children.Add(sourceArea);
        var footer = new DockPanel { Margin = new Thickness(10, 4, 10, 10) };
        Grid.SetRow(footer, 2); composerGrid.Children.Add(footer);
        var send = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
        DockPanel.SetDock(send, Dock.Right); footer.Children.Add(send);
        send.Children.Add(Theme.Text("译为", 12.5, "TextFaint").With(t => { t.VerticalAlignment = VerticalAlignment.Center; t.Margin = new Thickness(0, 0, 8, 0); }));
        target.Items.Add("自动");
        foreach (var name in Languages.Common) target.Items.Add(name);
        target.SelectedIndex = 0; send.Children.Add(target);
        translate = new Button { Content = Theme.IconText(Theme.IconSend, "翻译", 13), Margin = new Thickness(8, 0, 0, 0), MinWidth = 92, ToolTip = "翻译 (Ctrl+Enter)" }.Styled("Primary");
        translate.Click += async (_, _) => await TranslateAsync();
        send.Children.Add(translate);
        cancel = new Button { Content = Theme.IconText(Theme.IconCancel, "取消", 11), Margin = new Thickness(8, 0, 0, 0), MinWidth = 96, Visibility = Visibility.Collapsed, ToolTip = "取消 (Esc)" };
        cancel.Click += (_, _) => active?.Cancel();
        send.Children.Add(cancel);
        var tools = new WrapPanel { VerticalAlignment = VerticalAlignment.Center };
        footer.Children.Add(tools);
        tools.Children.Add(Tool(Theme.IconPaste, "剪贴板翻译", $"翻译剪贴板文本或图片 ({HotkeyManager.Label(Hotkey.Clipboard)})", async (_, _) => await TranslateClipboardAsync()));
        tools.Children.Add(Tool(Theme.IconCrop, "截图翻译", $"截图翻译 ({HotkeyManager.Label(Hotkey.Capture)})", async (_, _) => await CaptureAsync(true)));
        tools.Children.Add(Tool(Theme.IconScan, "截图 OCR", $"截图识别文字 ({HotkeyManager.Label(Hotkey.CaptureOcr)})", async (_, _) => await CaptureAsync(false)));
        tools.Children.Add(Tool(Theme.IconImage, "图片 OCR", "识别图片文件中的文字", async (_, _) => await OpenImageAsync()));
        composerGrid.Children.Add(progress); Grid.SetRow(progress, 2);
        var composer = Theme.Card(composerGrid, new Thickness(0), 14);
        DockPanel.SetDock(composer, Dock.Top); root.Children.Add(composer);

        status.Margin = new Thickness(6, 10, 6, 4); status.TextTrimming = TextTrimming.CharacterEllipsis; status.TextWrapping = TextWrapping.NoWrap;
        DockPanel.SetDock(status, Dock.Top); root.Children.Add(status);

        var results = new Grid { Margin = new Thickness(0, 6, 0, 0) };
        var scroll = new ScrollViewer { Content = cards, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled, Padding = new Thickness(0, 0, 2, 0) };
        results.Children.Add(scroll);
        emptyState = BuildEmptyState(); results.Children.Add(emptyState);
        root.Children.Add(results);

        // Narrow windows keep icon-only tools (labels stay available as tooltips).
        root.SizeChanged += (_, _) => { var mode = root.ActualWidth < 680 ? Visibility.Collapsed : Visibility.Visible; foreach (var label in toolLabels) label.Visibility = mode; };
        PreviewKeyDown += async (_, e) => { if (e.Key == Key.Enter && (Keyboard.Modifiers & ModifierKeys.Control) != 0) { e.Handled = true; await TranslateAsync(); } else if (e.Key == Key.Escape) { if (busy) active?.Cancel(); else Hide(); } };
        if (desktopIntegration) SourceInitialized += (_, _) => InitializeDesktop();
        // Sign-out, shutdown and installer (Restart Manager) close requests must exit instead of hiding to the tray.
        if (Application.Current != null) Application.Current.SessionEnding += (_, _) => quitting = true;
        Closing += (_, e) => { if (!quitting) { e.Cancel = true; Hide(); } };
        Closed += (_, _) => {
            try { StopSpeech(); } finally { active?.Cancel(); warmup?.Cancel(); hotkeys?.Dispose(); tray?.Dispose(); OcrEngine.Shutdown(); }
        };
    }

    /// <summary>Card header: marker and title on the left, icon controls on the right.</summary>
    static DockPanel Header(UIElement marker, string title, string titleBrush, params UIElement[] controls)
    {
        var header = new DockPanel();
        if (controls.Length > 0) {
            var panel = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(8, -6, -8, -6) };
            foreach (var control in controls) panel.Children.Add(control);
            DockPanel.SetDock(panel, Dock.Right); header.Children.Add(panel);
        }
        var label = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center };
        label.Children.Add(marker);
        label.Children.Add(Theme.Text(title, 12.5, titleBrush, FontWeights.SemiBold).With(t => { t.Margin = new Thickness(8, 0, 0, 0); t.VerticalAlignment = VerticalAlignment.Center; t.TextTrimming = TextTrimming.CharacterEllipsis; t.TextWrapping = TextWrapping.NoWrap; }));
        header.Children.Add(label);
        return header;
    }
    Button Tool(string glyph, string label, string tip, RoutedEventHandler action)
    {
        var content = new StackPanel { Orientation = Orientation.Horizontal };
        content.Children.Add(Theme.Glyph(glyph, 15));
        var text = new TextBlock { Text = label, Margin = new Thickness(7, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center };
        toolLabels.Add(text); content.Children.Add(text);
        var b = new Button { Content = content, ToolTip = tip, Margin = new Thickness(0, 0, 2, 0), Padding = new Thickness(9, 0, 9, 0) }.Styled("Ghost");
        b.Click += action; return b;
    }
    FrameworkElement BuildEmptyState()
    {
        var panel = new StackPanel { HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 0, 24) };
        var mark = Theme.Mark(44); mark.Opacity = 0.9; mark.HorizontalAlignment = HorizontalAlignment.Center; panel.Children.Add(mark);
        panel.Children.Add(Theme.Text($"选中文字，按 {HotkeyManager.Label(Hotkey.Selection)} 翻译", 15, "Text", FontWeights.SemiBold).With(t => { t.HorizontalAlignment = HorizontalAlignment.Center; t.Margin = new Thickness(0, 14, 0, 4); }));
        var grid = new Grid { HorizontalAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 18, 0, 0) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(28) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var shortcuts = new[] { (Hotkey.Capture, "截图翻译"), (Hotkey.CaptureOcr, "截图 OCR"), (Hotkey.Clipboard, "剪贴板翻译"), (Hotkey.Input, "输入翻译") };
        for (int i = 0; i < shortcuts.Length; i++) {
            if (i % 2 == 0) grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var row = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 4, 0, 4) };
            row.Children.Add(Theme.Kbd(HotkeyManager.Label(shortcuts[i].Item1)).With(k => k.MinWidth = 52));
            row.Children.Add(Theme.Text(shortcuts[i].Item2, 12.5, "TextMuted").With(t => { t.Margin = new Thickness(10, 0, 0, 0); t.VerticalAlignment = VerticalAlignment.Center; }));
            Grid.SetRow(row, i / 2); Grid.SetColumn(row, i % 2 * 2); grid.Children.Add(row);
        }
        panel.Children.Add(grid);
        return panel;
    }
    void InitializeDesktop()
    {
        try {
            hotkeys = new HotkeyManager(this, key => Dispatcher.InvokeAsync(async () => await HandleHotkey(key)));
            if (hotkeys.Failed.Count > 0) SetStatus("快捷键已被其他程序占用：" + string.Join("、", hotkeys.Failed.Select(HotkeyManager.Label)));
        }
        catch (Exception ex) { SetStatus("快捷键注册失败：" + ex.Message); }
        using (var iconStream = Theme.IconStream())
            tray = new Forms.NotifyIcon { Icon = new System.Drawing.Icon(iconStream, Forms.SystemInformation.SmallIconSize), Text = "译取", Visible = true };
        var menu = new Forms.ContextMenuStrip();
        TrayMenuStyle.Apply(menu);
        menu.Items.Add(TrayMenuStyle.Item("输入翻译", HotkeyManager.Label(Hotkey.Input), () => Dispatcher.Invoke(ShowApp)));
        menu.Items.Add(TrayMenuStyle.Item("截图翻译", HotkeyManager.Label(Hotkey.Capture), () => Dispatcher.InvokeAsync(async () => await CaptureAsync(true))));
        menu.Items.Add(TrayMenuStyle.Item("截图 OCR", HotkeyManager.Label(Hotkey.CaptureOcr), () => Dispatcher.InvokeAsync(async () => await CaptureAsync(false))));
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add(TrayMenuStyle.Item("设置", null, () => Dispatcher.Invoke(ShowSettings)));
        menu.Items.Add(TrayMenuStyle.Item("退出", null, () => Dispatcher.Invoke(() => { quitting = true; Close(); Application.Current.Shutdown(); })));
        tray.ContextMenuStrip = menu; tray.DoubleClick += (_, _) => Dispatcher.Invoke(ShowApp);
        _ = WarmUpOcrAsync();
    }
    async Task WarmUpOcrAsync()
    {
        warmup?.Cancel();
        var cancellation = new CancellationTokenSource(); warmup = cancellation;
        bool localModel = settings.Ocr.Provider.Equals("rapidocr", StringComparison.OrdinalIgnoreCase);
        if (localModel && !busy) SetStatus("正在加载 OCR 模型…");
        try {
            await OcrEngine.WarmUpAsync(settings.Ocr, cancellation.Token);
            if (localModel && !busy && !cancellation.IsCancellationRequested && !quitting) SetStatus("");
        } catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
          catch (Exception ex) { if (!busy && !quitting) SetStatus("OCR 模型加载失败：" + ex.Message); }
        finally { if (ReferenceEquals(warmup, cancellation)) warmup = null; cancellation.Dispose(); }
    }
    async Task HandleHotkey(Hotkey key)
    {
        try {
            if (busy) { SetStatus("请等待当前任务完成"); return; }
            switch (key) {
                case Hotkey.Selection:
                    string selected; SetBusy(true);
                    try { selected = await NativeDesktop.ReadSelectionAsync(); } finally { SetBusy(false); }
                    ShowApp(); SetSource(selected);
                    if (string.IsNullOrWhiteSpace(selected)) SetStatus("未获取到选中的文字"); else await TranslateAsync(); break;
                case Hotkey.Capture: await CaptureAsync(true); break;
                case Hotkey.Input: ShowApp(); ClearPanel(); break;
                case Hotkey.CaptureOcr: await CaptureAsync(false); break;
                case Hotkey.Clipboard: ShowApp(); await TranslateClipboardAsync(); break;
            }
        } catch (Exception ex) { ShowApp(); SetStatus("操作失败：" + ex.Message); }
    }
    void ShowApp() { Show(); if (WindowState == WindowState.Minimized) WindowState = WindowState.Normal; Activate(); if (!IsKeyboardFocusWithin) input.Focus(); }
    async Task TranslateClipboardAsync()
    {
        if (busy) { SetStatus("请等待当前任务完成"); return; }
        try {
            // Always read fresh content; never fall back to the previous input when the clipboard is empty.
            var clipboard = ReadClipboard();
            if (clipboard?.GetDataPresent(DataFormats.Bitmap) == true) {
                var bitmap = clipboard.GetData(DataFormats.Bitmap) as BitmapSource;
                if (bitmap == null) { SetSource(""); SetStatus("无法读取剪贴板图片"); return; }
                await RecognizeImageAsync(EncodePng(bitmap), thenTranslate: true); return;
            }
            if (clipboard?.GetDataPresent(DataFormats.UnicodeText) != true) { SetSource(""); SetStatus("剪贴板中没有文本或图片"); return; }
            SetSource(clipboard.GetData(DataFormats.UnicodeText) as string ?? "");
            if (string.IsNullOrWhiteSpace(input.Text)) { SetStatus("剪贴板为空"); return; }
            await TranslateAsync();
        } catch (Exception ex) { SetStatus("无法读取剪贴板：" + ex.Message); }
    }
    async Task OpenImageAsync()
    {
        if (busy) { SetStatus("请等待当前任务完成"); return; }
        var dialog = new Microsoft.Win32.OpenFileDialog {
            Title = "选择图片", Filter = "图片文件|*.png;*.jpg;*.jpeg;*.bmp;*.tif;*.tiff;*.gif|所有文件|*.*", CheckFileExists = true, Multiselect = false
        };
        byte[]? image = null;
        SetBusy(true);
        try {
            if (dialog.ShowDialog(this) != true) return;
            using var stream = File.OpenRead(dialog.FileName);
            var bitmap = BitmapDecoder.Create(stream, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad).Frames[0];
            image = EncodePng(bitmap);
        } catch (Exception ex) { SetStatus("无法打开图片：" + ex.Message); }
        finally { SetBusy(false); }
        if (image != null) await RecognizeImageAsync(image, false);
    }
    static byte[] EncodePng(BitmapSource bitmap)
    {
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using var stream = new MemoryStream(); encoder.Save(stream); return stream.ToArray();
    }
    void SetStatus(string message) => status.Text = message;
    void SetBusy(bool value)
    {
        busy = value;
        clear.IsEnabled = !value;
        translate.Visibility = value ? Visibility.Collapsed : Visibility.Visible;
        cancel.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        progress.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
    }
    void ClearCards() { StopSpeech(); cards.Children.Clear(); resultViews.Clear(); emptyState.Visibility = Visibility.Visible; }
    void ClearPanel()
    {
        if (busy) return;
        ClearCards(); SetSource(""); SetStatus(""); input.Focus();
    }
    /// <summary>Sets the source text from outside the editor and refreshes the rendered view.</summary>
    void SetSource(string text) { input.Text = text; UpdateSourceView(); }
    /// <summary>Shows the preview when Markdown is on and there is text; otherwise the editor.</summary>
    void UpdateSourceView()
    {
        bool render = settings.MarkdownSource && !string.IsNullOrWhiteSpace(input.Text);
        if (render) MarkdownView.Show(sourceView, input.Text);
        sourceView.Visibility = render ? Visibility.Visible : Visibility.Collapsed;
        input.Visibility = render ? Visibility.Collapsed : Visibility.Visible;
    }
    /// <summary>Opens the editor at the source position under <paramref name="point"/> in the preview; links keep their click.</summary>
    internal bool EditSourceAt(Point point)
    {
        var position = sourceView.GetPositionFromPoint(point, true);
        if (position == null || InLink(position)) return false;
        EditSource(MarkdownView.SourceOffset(input.Text, new TextRange(sourceView.Document.ContentStart, position).Text));
        return true;
    }
    void EditSource(int caret)
    {
        sourceView.Visibility = Visibility.Collapsed; input.Visibility = Visibility.Visible;
        input.Focus(); input.Select(Math.Clamp(caret, 0, input.Text.Length), 0);
        Dispatcher.BeginInvoke(() => { int line = input.GetLineIndexFromCharacterIndex(input.CaretIndex); if (line >= 0) input.ScrollToLine(line); }, DispatcherPriority.Loaded);
    }
    static bool InLink(TextPointer position)
    {
        for (var element = position.Parent as FrameworkContentElement; element != null; element = element.Parent as FrameworkContentElement)
            if (element is Hyperlink) return true;
        return false;
    }
    void SetResultMarkdown(bool on)
    {
        settings.MarkdownResults = on; Persist();
        foreach (var (toggle, body) in resultViews) { toggle.IsChecked = on; body.Markdown = on; }
    }
    void Persist()
    {
        try { SaveSettings(settings); } catch (Exception ex) { SetStatus("设置保存失败：" + ex.Message); }
    }
    void CopyText(string text, Button button)
    {
        if (string.IsNullOrWhiteSpace(text)) return;
        try { Clipboard.SetText(text); SetStatus("已复制"); Flash(button); }
        catch (Exception ex) { SetStatus("复制失败：" + ex.Message); }
    }
    void ResetSpeechButton()
    {
        speechTimer.Stop();
        if (speakingButton != null) {
            speakingButton.Content = Theme.IconSpeak;
            speakingButton.ToolTip = "朗读";
            speakingButton.ClearValue(ForegroundProperty);
            speakingButton = null;
        }
    }
    void StopSpeech() { speechCancel?.Cancel(); speechCancel = null; Speech.Stop(); ResetSpeechButton(); }
    async void ToggleSpeech(Button button, string text)
    {
        bool stop = ReferenceEquals(button, speakingButton);
        StopSpeech();
        if (stop || string.IsNullOrWhiteSpace(text)) return;
        // The button shows stop while the text is synthesized, so a second click cancels before playback.
        speakingButton = button;
        button.Content = Theme.IconStop; button.ToolTip = "停止朗读";
        button.Ref(ForegroundProperty, "AccentText");
        var cancellation = new CancellationTokenSource(); speechCancel = cancellation;
        try {
            await Speech.SpeakAsync(text, cancellation.Token);
            if (ReferenceEquals(speechCancel, cancellation)) speechTimer.Start();
        } catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
          catch (Exception ex) { if (ReferenceEquals(speechCancel, cancellation)) { StopSpeech(); SetStatus("朗读失败：" + ex.Message); } }
    }
    async Task TranslateAsync()
    {
        if (busy) return;
        string text = input.Text.Trim();
        if (text.Length == 0) { SetStatus("请输入要翻译的文本"); return; }
        var services = settings.Services.Where(s => s.Enabled).ToList();
        if (services.Count == 0) { SetStatus("没有已启用的翻译服务，请在设置中添加"); return; }
        string language = (string?)target.SelectedItem ?? "自动", shown = language;
        if (language == "自动") {
            language = TranslationEngine.ResolveTarget(text, settings);
            // A non-Chinese primary language resolves to a conditional prompt phrase; history shows the pair instead.
            shown = language == settings.PrimaryLanguage || language == settings.SecondaryLanguage ? language : $"{settings.PrimaryLanguage} / {settings.SecondaryLanguage}";
        }
        active = new CancellationTokenSource(); SetBusy(true); ClearCards();
        SetStatus("正在翻译…");
        var results = new List<TranslationResult>();
        try {
            await TranslationEngine.TranslateAsync(text, language, services, result => Dispatcher.Invoke(() => { results.Add(result); AddCard(result); }), active.Token);
            int failed = results.Count(r => r.Error != null);
            SetStatus(active.IsCancellationRequested ? "已取消" : failed > 0 ? $"{failed} 个服务失败" : "");
            if (settings.SaveHistory && results.Any(r => r.Error == null)) {
                try { HistoryStore.Add(new HistoryEntry { Source = text, Target = shown, Results = results }); }
                catch (Exception ex) { SetStatus("历史记录保存失败：" + ex.Message); }
            }
        } catch (OperationCanceledException) { SetStatus("已取消"); }
          catch (Exception ex) { SetStatus("翻译失败：" + ex.Message); }
        finally { active.Dispose(); active = null; SetBusy(false); }
    }
    void AddCard(TranslationResult result, string? glyph = null)
    {
        bool failed = result.Error != null;
        // Translations can carry Markdown; OCR output (cards with a glyph) is shown as recognized.
        bool markdown = !failed && glyph == null;
        var controls = new List<UIElement>();
        ToggleButton? toggle = null;
        if (markdown) {
            toggle = Theme.MarkdownToggle(settings.MarkdownResults);
            toggle.Click += (_, _) => SetResultMarkdown(toggle.IsChecked == true);
            controls.Add(toggle);
        }
        if (!failed) {
            Button? copy = null, speak = null;
            copy = Theme.IconButton(Theme.IconCopy, "复制", (_, _) => CopyText(result.Text, copy!));
            speak = Theme.IconButton(Theme.IconSpeak, "朗读", (_, _) => ToggleSpeech(speak!, markdown && settings.MarkdownResults ? MarkdownView.PlainText(result.Text) : result.Text));
            controls.Add(copy); controls.Add(speak);
        }
        UIElement marker = failed ? Theme.Glyph(Theme.IconError, 13, "Danger")
            : glyph != null ? Theme.Glyph(glyph, 13, "AccentText")
            : Theme.ServiceDot(result.ServiceName);
        var panel = new DockPanel();
        var header = Header(marker, result.ServiceName, failed ? "Danger" : "TextMuted", controls.ToArray());
        header.Margin = new Thickness(0, 0, 0, 8);
        DockPanel.SetDock(header, Dock.Top); panel.Children.Add(header);
        if (failed) panel.Children.Add(MarkdownView.PassWheel(new TextBox { Text = result.Error!, FontSize = 13.5 }.Styled("ReadOnlyText").Ref(ForegroundProperty, "Danger")));
        else {
            var body = new MarkdownText(result.Text, 15.5, markdown && settings.MarkdownResults);
            if (toggle != null) resultViews.Add((toggle, body));
            panel.Children.Add(body);
        }
        var card = Theme.Card(panel, new Thickness(18, 14, 18, 16), 12, shadow: !failed);
        if (failed && card is Border border) border.Ref(Border.BackgroundProperty, "DangerSoft").Ref(Border.BorderBrushProperty, "DangerStroke");
        card.Margin = new Thickness(0, 0, 0, 12);
        cards.Children.Add(card);
        emptyState.Visibility = Visibility.Collapsed;
    }
    static void Flash(Button button)
    {
        button.Content = Theme.IconCheck; button.Ref(ForegroundProperty, "AccentText");
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1.2) };
        timer.Tick += (_, _) => { timer.Stop(); button.Content = Theme.IconCopy; button.ClearValue(ForegroundProperty); };
        timer.Start();
    }
    async Task CaptureAsync(bool thenTranslate)
    {
        if (busy) { SetStatus("请等待当前任务完成"); return; }
        byte[]? image;
        SetBusy(true);
        Hide();
        try { await Task.Delay(120); image = await CaptureOverlay.CaptureAsync(); }
        catch (Exception ex) { ShowApp(); SetBusy(false); SetStatus("截图失败：" + ex.Message); return; }
        ShowApp(); SetBusy(false); if (image == null) { SetStatus(""); return; }
        await RecognizeImageAsync(image, thenTranslate);
    }
    async Task RecognizeImageAsync(byte[] image, bool thenTranslate)
    {
        if (busy) { SetStatus("请等待当前任务完成"); return; }
        active = new CancellationTokenSource(); SetBusy(true); SetStatus("正在识别文字…");
        string? recognized = null;
        try {
            var result = await OcrEngine.RecognizeAsync(image, settings.Ocr, active.Token);
            recognized = result.Text; SetSource(result.Text);
            if (string.IsNullOrWhiteSpace(result.Text)) SetStatus("未识别到文字");
            else if (!thenTranslate) { ClearCards(); AddCard(new TranslationResult("识别结果 · " + result.Provider, result.Text), Theme.IconScan); SetStatus(""); }
        } catch (OperationCanceledException) { SetStatus("已取消"); }
          catch (Exception ex) { SetStatus("识别失败：" + ex.Message); }
        finally { active.Dispose(); active = null; SetBusy(false); }
        if (thenTranslate && !string.IsNullOrWhiteSpace(recognized)) await TranslateAsync();
    }
    internal void SetVerificationContent(string text, IReadOnlyList<TranslationResult> results, string message, bool busyState = false)
    {
        SetSource(text); ClearCards();
        foreach (var result in results) AddCard(result);
        SetStatus(message);
        if (busyState) SetBusy(true);
    }
    void ShowSettings()
    {
        ShowApp();
        if (busy) { SetStatus("请等待当前任务完成"); return; }
        var window = new SettingsWindow(settings) { Owner = this };
        if (window.ShowDialog() == true && window.Result != null) { settings = window.Result; SetStatus("设置已保存"); _ = WarmUpOcrAsync(); }
    }
    void ShowHistory() { if (busy) { SetStatus("请等待当前任务完成"); return; } try { new HistoryWindow(text => { SetSource(text); ShowApp(); }, settings.MarkdownResults, SetResultMarkdown) { Owner = this }.ShowDialog(); } catch (Exception ex) { SetStatus("读取历史失败：" + ex.Message); } }
}
