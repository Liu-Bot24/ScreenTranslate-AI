using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.IO;
using System.Threading;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace YiQu;

public sealed class SettingsWindow : ShellWindow
{
    readonly AppSettings draft;
    readonly TabControl tabs = new();
    readonly StackPanel servicePanels = new();
    readonly List<Action> saveFields = new();
    readonly TextBlock error = Theme.Text("", 12.5, "Danger").With(t => t.VerticalAlignment = VerticalAlignment.Center);
    readonly Button save;
    CancellationTokenSource? download;
    public AppSettings? Result { get; private set; }
    public SettingsWindow(AppSettings current) : base("设置", dialog: true)
    {
        draft = JsonSerializer.Deserialize<AppSettings>(JsonSerializer.Serialize(current)) ?? new();
        Title = "设置 · 译取"; Width = 860; Height = 720; MinWidth = 660; MinHeight = 480;
        WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var root = new DockPanel(); Body = root;

        var footer = new DockPanel { Margin = new Thickness(24, 12, 20, 14) };
        var footerHost = new Border { Child = footer, BorderThickness = new Thickness(0, 1, 0, 0) }.Ref(Border.BorderBrushProperty, "Stroke").Ref(Border.BackgroundProperty, "Surface");
        DockPanel.SetDock(footerHost, Dock.Bottom); root.Children.Add(footerHost);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal };
        DockPanel.SetDock(buttons, Dock.Right); footer.Children.Add(buttons);
        buttons.Children.Add(Theme.TextButton("取消", (_, _) => DialogResult = false).With(b => b.MinWidth = 88));
        save = Theme.TextButton("保存", (_, _) => Save(), "Primary").With(b => { b.MinWidth = 88; b.Margin = new Thickness(10, 0, 0, 0); });
        buttons.Children.Add(save);
        footer.Children.Add(error);

        tabs.Styled("NavTabs"); root.Children.Add(tabs);
        var translations = Page("翻译服务", "可同时启用多个服务，结果分别显示。支持 OpenAI 兼容接口。");
        translations.Children.Add(servicePanels);
        foreach (var service in draft.Services.ToArray()) AddService(service);
        translations.Children.Add(Theme.TextButton("添加翻译服务", (_, _) => {
            var service = new TranslationService { Name = "新服务", Enabled = true, Endpoint = "", Model = "" };
            draft.Services.Add(service); AddService(service, expand: true);
        }, "Dashed", Theme.IconAdd).With(b => b.Margin = new Thickness(0, 2, 0, 0)));
        tabs.Items.Add(new TabItem { Header = Theme.IconText(Theme.IconTranslate, "翻译服务"), Content = Scroll(translations) });
        tabs.Items.Add(new TabItem { Header = Theme.IconText(Theme.IconScan, "文字识别 OCR"), Content = Scroll(BuildOcr()) });
        tabs.Items.Add(new TabItem { Header = Theme.IconText(Theme.IconSettings, "常规"), Content = Scroll(BuildGeneral()) });
        Closing += (_, _) => download?.Cancel();
    }
    internal void SelectVerificationTab(int index)
    {
        tabs.SelectedIndex = index;
        if (index == 0 && servicePanels.Children.Count > 0 && servicePanels.Children[0] is Expander first) first.IsExpanded = true;
    }
    static ScrollViewer Scroll(UIElement content) => new() { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled };
    static StackPanel Page(string title, string? description = null)
    {
        var page = new StackPanel { Margin = new Thickness(12, 4, 28, 28), MaxWidth = 760, HorizontalAlignment = HorizontalAlignment.Stretch };
        page.Children.Add(Theme.Text(title, 20, "Text", FontWeights.SemiBold).With(t => t.Margin = new Thickness(0, 0, 0, description == null ? 16 : 0)));
        if (description != null) page.Children.Add(Theme.Text(description, 12.5, "TextMuted").With(t => t.Margin = new Thickness(0, 6, 0, 18)));
        return page;
    }
    /// <summary>Language dropdown with a trailing custom entry that reveals a text box; returns the chosen value.</summary>
    static Func<string> LanguagePicker(Panel panel, string label, string value)
    {
        const string Custom = "自定义…";
        panel.Children.Add(Label(label));
        var combo = new ComboBox();
        foreach (var name in Languages.Common) combo.Items.Add(name);
        combo.Items.Add(Custom);
        var custom = new TextBox { Tag = "输入语言名称", Margin = new Thickness(0, 8, 0, 0) };
        bool known = Array.IndexOf(Languages.Common, value) >= 0;
        combo.SelectedItem = known ? value : Custom;
        if (!known) custom.Text = value;
        bool IsCustom() => Equals(combo.SelectedItem, Custom);
        custom.Visibility = IsCustom() ? Visibility.Visible : Visibility.Collapsed;
        combo.SelectionChanged += (_, _) => {
            custom.Visibility = IsCustom() ? Visibility.Visible : Visibility.Collapsed;
            if (IsCustom()) custom.Focus();
        };
        panel.Children.Add(combo); panel.Children.Add(custom);
        return () => IsCustom() ? custom.Text.Trim() : (string)combo.SelectedItem;
    }
    /// <summary>Titled card section inside a settings page; returns the panel to fill.</summary>
    static StackPanel Section(Panel page, string title, string? description = null)
    {
        var panel = new StackPanel();
        panel.Children.Add(Theme.Text(title, 14, "Text", FontWeights.SemiBold));
        if (description != null) panel.Children.Add(Theme.Text(description, 12.5, "TextMuted").With(t => t.Margin = new Thickness(0, 4, 0, 0)));
        var card = Theme.Card(panel, new Thickness(20, 16, 20, 20), 12, shadow: false);
        card.Margin = new Thickness(0, 0, 0, 14);
        page.Children.Add(card);
        return panel;
    }
    static TextBlock Note(string text) => Theme.Text(text, 12, "TextFaint").With(t => t.Margin = new Thickness(0, 8, 0, 0));
    static TextBox Field(Panel panel, string label, string value, bool multiline = false, string? hint = null)
    {
        panel.Children.Add(Label(label));
        var box = new TextBox { Text = value, Tag = hint, MinHeight = multiline ? 92 : 34, AcceptsReturn = multiline, TextWrapping = multiline ? TextWrapping.Wrap : TextWrapping.NoWrap, VerticalScrollBarVisibility = multiline ? ScrollBarVisibility.Auto : ScrollBarVisibility.Hidden };
        if (multiline) box.VerticalContentAlignment = VerticalAlignment.Top;
        panel.Children.Add(box); return box;
    }
    static TextBlock Label(string text) => Theme.Text(text, 12.5, "TextMuted", FontWeights.Medium).With(t => t.Margin = new Thickness(0, 14, 0, 6));
    PasswordBox SecretField(Panel panel, string value)
    {
        panel.Children.Add(Label("API Key"));
        var password = new PasswordBox();
        try { password.Password = string.IsNullOrEmpty(value) ? "" : Secrets.Unprotect(value); }
        catch { error.Text = "部分 API Key 无法解密，请重新填写"; password.Tag = value; }
        password.PasswordChanged += (_, _) => password.Tag = null;
        panel.Children.Add(password); return password;
    }
    static string ProtectedSecret(PasswordBox box) => box.Tag is string original ? original : (string.IsNullOrEmpty(box.Password) ? "" : Secrets.Protect(box.Password));
    void AddService(TranslationService service, bool expand = false)
    {
        var panel = new StackPanel();
        var enabled = new CheckBox { Content = "启用", IsChecked = service.Enabled, Margin = new Thickness(0, 12, 0, 2) }; panel.Children.Add(enabled);
        var name = Field(panel, "名称", service.Name, hint: "例如 我的翻译服务");
        var endpoint = Field(panel, "接口地址", service.Endpoint, hint: "https://api.example.com/v1/chat/completions");
        var model = Field(panel, "模型", service.Model, hint: "例如 example-model");
        var key = SecretField(panel, service.ProtectedApiKey);
        var prompt = Field(panel, "系统提示词", service.SystemPrompt, true);
        panel.Children.Add(Note("{target} 代表目标语言"));

        // Header: colored initial, name with model subtitle, enabled pill.
        var header = new DockPanel();
        var pillText = Theme.Text("", 11.5, "AccentText", FontWeights.SemiBold);
        var pill = new Border { CornerRadius = new CornerRadius(10), Padding = new Thickness(9, 2, 9, 3), VerticalAlignment = VerticalAlignment.Center, Child = pillText };
        DockPanel.SetDock(pill, Dock.Right); header.Children.Add(pill);
        var initial = new TextBlock { Foreground = Brushes.White, FontWeight = FontWeights.SemiBold, FontSize = 13, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center };
        var badge = new Border { Width = 32, Height = 32, CornerRadius = new CornerRadius(8), Child = initial, Margin = new Thickness(0, 0, 12, 0) };
        header.Children.Add(badge);
        var titles = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        var titleText = Theme.Text("", 14, "Text", FontWeights.SemiBold).With(t => { t.TextWrapping = TextWrapping.NoWrap; t.TextTrimming = TextTrimming.CharacterEllipsis; });
        var subtitle = Theme.Text("", 12, "TextFaint").With(t => { t.TextWrapping = TextWrapping.NoWrap; t.TextTrimming = TextTrimming.CharacterEllipsis; t.Margin = new Thickness(0, 2, 0, 0); });
        titles.Children.Add(titleText); titles.Children.Add(subtitle); header.Children.Add(titles);
        void Refresh()
        {
            string display = string.IsNullOrWhiteSpace(name.Text) ? "新服务" : name.Text.Trim();
            titleText.Text = display; initial.Text = display[..1].ToUpperInvariant();
            badge.Background = new SolidColorBrush(Theme.BadgeColor(display));
            string host = Uri.TryCreate(endpoint.Text.Trim(), UriKind.Absolute, out var uri) ? uri.Host : "未填写地址";
            subtitle.Text = (string.IsNullOrWhiteSpace(model.Text) ? "未填写模型" : model.Text.Trim()) + " · " + host;
            bool on = enabled.IsChecked == true;
            pillText.Text = on ? "已启用" : "未启用";
            pillText.Ref(TextBlock.ForegroundProperty, on ? "AccentText" : "TextFaint");
            pill.Ref(Border.BackgroundProperty, on ? "AccentSoft" : "SurfaceAlt");
        }
        name.TextChanged += (_, _) => Refresh(); model.TextChanged += (_, _) => Refresh(); endpoint.TextChanged += (_, _) => Refresh();
        enabled.Checked += (_, _) => Refresh(); enabled.Unchecked += (_, _) => Refresh();
        Refresh();

        var expander = new Expander { Header = header, Content = panel, IsExpanded = expand || draft.Services.Count <= 1, Margin = new Thickness(0, 0, 0, 12) };
        Action commit = () => {
            service.Name = name.Text.Trim(); service.Enabled = enabled.IsChecked == true;
            service.Endpoint = endpoint.Text.Trim(); service.Model = model.Text.Trim(); service.SystemPrompt = prompt.Text;
            service.ProtectedApiKey = ProtectedSecret(key);
            if (service.Enabled) {
                if (string.IsNullOrWhiteSpace(service.Name) || string.IsNullOrWhiteSpace(service.Model)) throw new InvalidOperationException("请填写服务名称和模型");
                ValidateEndpoint(service.Endpoint, service.Name);
            }
        };
        saveFields.Add(commit);
        panel.Children.Add(Theme.TextButton("删除服务", (_, _) => { draft.Services.Remove(service); saveFields.Remove(commit); servicePanels.Children.Remove(expander); }, "DangerButton", Theme.IconDelete)
            .With(b => { b.HorizontalAlignment = HorizontalAlignment.Left; b.Margin = new Thickness(-10, 14, 0, 0); }));
        servicePanels.Children.Add(expander);
    }
    UIElement BuildOcr()
    {
        var page = Page("文字识别 OCR", "Windows OCR、RapidOCR 和 Tesseract 在本机识别；视觉模型会将截图发送到所配置的服务。");
        var engine = Section(page, "识别引擎");
        var provider = new ComboBox { Margin = new Thickness(0, 12, 0, 0), SelectedValuePath = "Tag", MinHeight = 38 };
        provider.Items.Add(new ComboBoxItem { Content = "Windows OCR", Tag = "windows" });
        provider.Items.Add(new ComboBoxItem { Content = "RapidOCR", Tag = "rapidocr" });
        provider.Items.Add(new ComboBoxItem { Content = "Tesseract", Tag = "tesseract" });
        provider.Items.Add(new ComboBoxItem { Content = "视觉模型（在线）", Tag = "vision" });
        provider.SelectedValue = draft.Ocr.Provider;
        if (provider.SelectedIndex < 0) provider.SelectedIndex = 0;
        engine.Children.Add(provider);
        var options = Section(page, "引擎设置");
        var windows = new StackPanel(); var rapid = new StackPanel(); var tess = new StackPanel(); var vision = new StackPanel();
        options.Children.Add(windows); options.Children.Add(rapid); options.Children.Add(tess); options.Children.Add(vision);
        var language = Field(windows, "识别语言", draft.Ocr.Language, hint: "例如 zh-Hans");
        try { windows.Children.Add(Note("可用语言：" + string.Join("、", OcrEngine.AvailableWindowsLanguages()))); }
        catch (Exception ex) { windows.Children.Add(Note("无法获取可用语言：" + ex.Message)); }
        windows.Children.Add(Note("也可下载 RapidOCR，使用本地 PP-OCRv5 模型识别。"));
        windows.Children.Add(Theme.TextButton("设置 RapidOCR", (_, _) => provider.SelectedValue = "rapidocr")
            .With(b => { b.HorizontalAlignment = HorizontalAlignment.Left; b.Margin = new Thickness(0, 12, 0, 0); }));
        string? installedPython = RapidOcrRuntime.InstalledPython();
        rapid.Children.Add(Note($"首次下载约 {RapidOcrRuntime.DownloadBytes / 1048576.0:F0} MB，包含运行环境和模型，无需安装 Python。下载后可离线识别。"));
        var componentStatus = Theme.Text(installedPython == null ? "尚未下载" : "组件已就绪", 12.5, "TextMuted").With(t => t.Margin = new Thickness(0, 14, 0, 0));
        rapid.Children.Add(componentStatus);
        var controls = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 12, 0, 0) };
        rapid.Children.Add(controls);
        var install = new Button { Content = installedPython == null ? "下载并安装" : "检查组件", MinWidth = 100 }.Styled("Primary");
        var cancelDownload = Theme.TextButton("取消下载", (_, _) => download?.Cancel()).With(b => { b.Visibility = Visibility.Collapsed; b.Margin = new Thickness(8, 0, 0, 0); });
        controls.Children.Add(install); controls.Children.Add(cancelDownload);
        var customPanel = new StackPanel();
        var python = Field(customPanel, "Python 路径", draft.Ocr.LocalPythonPath, hint: "已安装 RapidOCR 的 python.exe");
        bool hasCustom = !string.IsNullOrWhiteSpace(draft.Ocr.LocalPythonPath) && !string.Equals(draft.Ocr.LocalPythonPath, installedPython, StringComparison.OrdinalIgnoreCase);
        var custom = new CheckBox { Content = "使用自定义 Python 环境", IsChecked = hasCustom, Margin = new Thickness(0, 18, 0, 0) };
        rapid.Children.Add(custom); rapid.Children.Add(customPanel);
        customPanel.Visibility = hasCustom ? Visibility.Visible : Visibility.Collapsed;
        custom.Checked += (_, _) => customPanel.Visibility = Visibility.Visible;
        custom.Unchecked += (_, _) => customPanel.Visibility = Visibility.Collapsed;
        install.Click += async (_, _) => {
            if (download != null) return;
            using var cancellation = new CancellationTokenSource(); download = cancellation;
            install.IsEnabled = false; save.IsEnabled = false; provider.IsEnabled = false; custom.IsEnabled = false;
            cancelDownload.Visibility = Visibility.Visible; componentStatus.Text = "正在准备下载…";
            try {
                var progress = new Progress<RuntimeProgress>(p => componentStatus.Text = p.Percent is double value ? $"{p.Message} · {value:F0}%" : p.Message);
                installedPython = await RapidOcrRuntime.InstallAsync(progress, cancellation.Token);
                custom.IsChecked = false; componentStatus.Text = "组件已就绪，保存后启用"; install.Content = "检查组件";
            } catch (OperationCanceledException) { componentStatus.Text = "已取消，可重新下载"; }
            catch (Exception ex) { componentStatus.Text = ex is System.Net.Http.HttpRequestException ? "下载失败，请检查网络后重试" : "安装失败：" + ex.Message; }
            finally {
                download = null; install.IsEnabled = true; save.IsEnabled = true; provider.IsEnabled = true; custom.IsEnabled = true;
                cancelDownload.Visibility = Visibility.Collapsed;
            }
        };
        var path = Field(tess, "程序路径", draft.Ocr.TesseractPath, hint: "tesseract.exe");
        var languages = Field(tess, "识别语言", draft.Ocr.TesseractLanguages, hint: "例如 chi_sim+eng");
        var endpoint = Field(vision, "接口地址", draft.Ocr.Endpoint, hint: "https://…/v1/chat/completions");
        var model = Field(vision, "模型", draft.Ocr.Model, hint: "需支持图片输入");
        var key = SecretField(vision, draft.Ocr.ProtectedApiKey);
        void UpdateVisibility() {
            var value = provider.SelectedValue as string;
            windows.Visibility = value == "windows" ? Visibility.Visible : Visibility.Collapsed;
            rapid.Visibility = value == "rapidocr" ? Visibility.Visible : Visibility.Collapsed;
            tess.Visibility = value == "tesseract" ? Visibility.Visible : Visibility.Collapsed;
            vision.Visibility = value == "vision" ? Visibility.Visible : Visibility.Collapsed;
        }
        provider.SelectionChanged += (_, _) => UpdateVisibility(); UpdateVisibility();
        saveFields.Add(() => {
            draft.Ocr.Provider = provider.SelectedValue as string ?? "windows"; draft.Ocr.Language = language.Text.Trim();
            draft.Ocr.LocalPythonPath = custom.IsChecked == true ? python.Text.Trim() : installedPython ?? ""; draft.Ocr.TesseractPath = path.Text.Trim(); draft.Ocr.TesseractLanguages = languages.Text.Trim();
            draft.Ocr.Endpoint = endpoint.Text.Trim(); draft.Ocr.Model = model.Text.Trim();
            draft.Ocr.ProtectedApiKey = ProtectedSecret(key);
            if (draft.Ocr.Provider == "vision") { ValidateEndpoint(draft.Ocr.Endpoint, "视觉 OCR"); if (string.IsNullOrWhiteSpace(draft.Ocr.Model)) throw new InvalidOperationException("请填写视觉模型名称"); }
            if (draft.Ocr.Provider == "rapidocr" && !File.Exists(draft.Ocr.LocalPythonPath)) throw new InvalidOperationException("请先下载 RapidOCR 组件，或选择有效的自定义环境");
        });
        return page;
    }
    UIElement BuildGeneral()
    {
        var page = Page("常规");
        var historySection = Section(page, "翻译历史");
        var history = new CheckBox { Content = "保存翻译历史", IsChecked = draft.SaveHistory, Margin = new Thickness(0, 14, 0, 0) }; historySection.Children.Add(history);

        var languageSection = Section(page, "自动目标语言", "原文是主要语言时译为次要语言，否则译为主要语言。");
        var pair = new Grid();
        pair.ColumnDefinitions.Add(new ColumnDefinition()); pair.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(16) }); pair.ColumnDefinitions.Add(new ColumnDefinition());
        var left = new StackPanel(); var right = new StackPanel(); Grid.SetColumn(right, 2);
        pair.Children.Add(left); pair.Children.Add(right); languageSection.Children.Add(pair);
        var primary = LanguagePicker(left, "主要语言", draft.PrimaryLanguage);
        var secondary = LanguagePicker(right, "次要语言", draft.SecondaryLanguage);

        var keys = Section(page, "快捷键");
        var list = new Grid { Margin = new Thickness(0, 10, 0, 0) };
        list.ColumnDefinitions.Add(new ColumnDefinition()); list.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var shortcuts = new[] { ("划词翻译", "Alt+Q"), ("截图翻译", "Alt+W"), ("输入翻译", "Alt+E"), ("截图 OCR", "Alt+R"), ("剪贴板翻译", "Alt+C"), ("翻译输入内容", "Ctrl+Enter"), ("取消 / 隐藏窗口", "Esc") };
        for (int i = 0; i < shortcuts.Length; i++) {
            list.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var row = new Border { BorderThickness = new Thickness(0, i == 0 ? 0 : 1, 0, 0), Padding = new Thickness(0, 9, 0, 9) }.Ref(Border.BorderBrushProperty, "Stroke");
            Grid.SetRow(row, i); Grid.SetColumnSpan(row, 2); list.Children.Add(row);
            var label = Theme.Text(shortcuts[i].Item1, 13, "Text").With(t => { t.VerticalAlignment = VerticalAlignment.Center; t.Margin = new Thickness(0, 9, 0, 9); });
            Grid.SetRow(label, i); list.Children.Add(label);
            var kbd = Theme.Kbd(shortcuts[i].Item2); Grid.SetRow(kbd, i); Grid.SetColumn(kbd, 1); list.Children.Add(kbd);
        }
        keys.Children.Add(list);
        saveFields.Add(() => { draft.SaveHistory = history.IsChecked == true; draft.PrimaryLanguage = primary(); draft.SecondaryLanguage = secondary(); if (draft.PrimaryLanguage.Length == 0 || draft.SecondaryLanguage.Length == 0) throw new InvalidOperationException("请填写自定义语言名称"); if (draft.PrimaryLanguage == draft.SecondaryLanguage) throw new InvalidOperationException("主要语言和次要语言不能相同"); });
        return page;
    }
    static void ValidateEndpoint(string value, string name)
    {
        try { ChatApi.ValidateEndpoint(value); }
        catch (ArgumentException ex) { throw new InvalidOperationException(name + "：" + ex.Message); }
    }
    void Save()
    {
        if (download != null) return;
        try { foreach (var commit in saveFields) commit(); if (draft.Services.Count(s => s.Enabled) > TranslationEngine.MaxServices) throw new InvalidOperationException($"最多同时启用 {TranslationEngine.MaxServices} 个翻译服务"); SettingsStore.Save(draft); Result = draft; DialogResult = true; }
        catch (Exception ex) { error.Text = "无法保存：" + ex.Message; }
    }
}
