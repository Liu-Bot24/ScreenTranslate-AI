using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using Microsoft.Win32;

namespace YiQu;

/// <summary>
/// Light/dark palette (follows the Windows app theme) plus the control styles in Theme.xaml.
/// Code-built elements reference palette keys with SetResourceReference so a theme switch repaints them.
/// </summary>
public static class Theme
{
    public static readonly FontFamily UiFont = new("Segoe UI Variable Text, Segoe UI, Microsoft YaHei UI");
    public static readonly FontFamily IconFont = new("Segoe Fluent Icons, Segoe MDL2 Assets");
    static readonly Dictionary<string, (uint Light, uint Dark)> colors = new() {
        ["Bg"] = (0xF3F4F7, 0x16171B),
        ["Surface"] = (0xFFFFFF, 0x202127),
        ["SurfaceAlt"] = (0xF1F3F6, 0x2A2C33),
        ["SurfaceHover"] = (0xE7EAEF, 0x34363E),
        ["Field"] = (0xFBFBFD, 0x1B1C21),
        ["Stroke"] = (0xE4E7EC, 0x2E3037),
        ["StrokeStrong"] = (0xD3D8E0, 0x3D4049),
        ["Text"] = (0x191C22, 0xECEDF1),
        ["TextMuted"] = (0x5A616E, 0xA4A9B4),
        ["TextFaint"] = (0x8C93A0, 0x737985),
        ["Accent"] = (0x3C64F0, 0x5C82FF),
        ["AccentHover"] = (0x3357DB, 0x7093FF),
        ["AccentPressed"] = (0x2B4BC0, 0x4C72F0),
        ["AccentSoft"] = (0xEAEFFF, 0x232D4A),
        ["AccentText"] = (0x2E54D2, 0x94AFFF),
        ["OnAccent"] = (0xFFFFFF, 0xFFFFFF),
        ["Danger"] = (0xD13B3B, 0xF07070),
        ["DangerSoft"] = (0xFDEEEE, 0x3A2326),
        ["DangerStroke"] = (0xF4CACA, 0x5A3034),
        ["Star"] = (0xE8A317, 0xF2B63C),
        ["ScrollThumb"] = (0xC3C8D1, 0x4A4D57),
        ["CaptionCloseHover"] = (0xC42B1C, 0xC42B1C),
    };
    // Service badges: mid-saturation hues that read on both palettes.
    static readonly Color[] badges = { Rgb(0x3C64F0), Rgb(0x0F9F8F), Rgb(0x8E4EC6), Rgb(0xE07A12), Rgb(0xD6409F), Rgb(0x0B8FCF), Rgb(0x5F9E1B) };
    static readonly ResourceDictionary palette = new();
    static ResourceDictionary? styles;
    static bool listening;
    public static bool IsDark { get; private set; }
    public static event Action? Changed;

    /// <summary>Selects the palette. <paramref name="dark"/> = null follows Windows and tracks later changes.</summary>
    public static void Initialize(bool? dark = null)
    {
        IsDark = dark ?? SystemPrefersDark();
        Fill();
        if (dark == null && !listening) {
            listening = true;
            SystemEvents.UserPreferenceChanged += (_, e) => {
                if (e.Category != UserPreferenceCategory.General) return;
                var app = Application.Current;
                if (app == null) return;
                app.Dispatcher.InvokeAsync(() => {
                    bool next = SystemPrefersDark();
                    if (next == IsDark) return;
                    IsDark = next; Fill(); Changed?.Invoke();
                });
            };
        }
    }
    static bool SystemPrefersDark()
    {
        try {
            using var key = Registry.CurrentUser.OpenSubKey(@"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize");
            return key?.GetValue("AppsUseLightTheme") is int light && light == 0;
        } catch { return false; }
    }
    static void Fill()
    {
        foreach (var (name, pair) in colors) {
            var color = Rgb(IsDark ? pair.Dark : pair.Light);
            var brush = new SolidColorBrush(color); brush.Freeze();
            palette[name] = brush; palette[name + "Color"] = color;
        }
    }
    /// <summary>Makes the palette and control styles available to an element and its descendants.</summary>
    public static void Attach(FrameworkElement element) => Attach(element.Resources);
    public static void Attach(ResourceDictionary resources)
    {
        if (palette.Count == 0) Initialize();
        styles ??=(ResourceDictionary)Application.LoadComponent(new Uri("/YiQu;component/Theme.xaml", UriKind.Relative));
        resources.MergedDictionaries.Add(palette);
        resources.MergedDictionaries.Add(styles);
    }
    public static Color Rgb(uint value) => Color.FromRgb((byte)(value >> 16), (byte)(value >> 8), (byte)value);
    public static Color BadgeColor(string name)
    {
        int hash = 17; foreach (char c in name) hash = unchecked(hash * 31 + c);
        return badges[(hash & 0x7fffffff) % badges.Length];
    }

    public static T Ref<T>(this T element, DependencyProperty property, string key) where T : FrameworkElement
    {
        element.SetResourceReference(property, key); return element;
    }
    public static T Styled<T>(this T element, string key) where T : FrameworkElement => element.Ref(FrameworkElement.StyleProperty, key);
    public static T With<T>(this T element, Action<T> configure) { configure(element); return element; }

    public static Button TextButton(string label, RoutedEventHandler action, string style = "Secondary", string? glyph = null)
    {
        var button = new Button { Content = glyph == null ? label : IconText(glyph, label, 13) }.Styled(style);
        button.Click += action; return button;
    }
    public static Button IconButton(string glyph, string tip, RoutedEventHandler action)
    {
        var button = new Button { Content = glyph, ToolTip = tip, Margin = new Thickness(2, 0, 2, 0) }.Styled("IconButton");
        button.Click += action; return button;
    }
    /// <summary>The "M" toggle that switches a text view between plain text and rendered Markdown.</summary>
    public static ToggleButton MarkdownToggle(bool on) =>
        new ToggleButton { Content = new TextBlock { Text = "M", FontFamily = UiFont, FontWeight = FontWeights.SemiBold, FontSize = 13 }, IsChecked = on, ToolTip = "Markdown 渲染", Margin = new Thickness(2, 0, 2, 0), Focusable = false }.Styled("IconToggle");
    /// <summary>Small round marker; services get a stable color derived from their name.</summary>
    public static Border Dot(Brush brush) => new() { Width = 8, Height = 8, CornerRadius = new CornerRadius(4), VerticalAlignment = VerticalAlignment.Center, Background = brush };
    public static Border Dot(string brushKey) => Dot(Brushes.Transparent).Ref(Border.BackgroundProperty, brushKey);
    public static Border ServiceDot(string serviceName) => Dot(new SolidColorBrush(BadgeColor(serviceName)));
    public static TextBlock Text(string text, double size = 13, string brush = "Text", FontWeight? weight = null) =>
        new TextBlock { Text = text, FontSize = size, FontWeight = weight ?? FontWeights.Normal, TextWrapping = TextWrapping.Wrap }.Ref(TextBlock.ForegroundProperty, brush);
    public static TextBlock Glyph(string glyph, double size = 14, string? brush = null)
    {
        var block = new TextBlock { Text = glyph, FontFamily = IconFont, FontSize = size, VerticalAlignment = VerticalAlignment.Center, HorizontalAlignment = HorizontalAlignment.Center };
        if (brush != null) block.Ref(TextBlock.ForegroundProperty, brush);
        return block;
    }
    public static StackPanel IconText(string glyph, string text, double iconSize = 14)
    {
        var panel = new StackPanel { Orientation = Orientation.Horizontal };
        panel.Children.Add(Glyph(glyph, iconSize));
        panel.Children.Add(new TextBlock { Text = text, Margin = new Thickness(8, 0, 0, 0), VerticalAlignment = VerticalAlignment.Center });
        return panel;
    }
    /// <summary>Keyboard shortcut chip, e.g. "Alt+Q".</summary>
    public static Border Kbd(string keys)
    {
        var border = new Border { CornerRadius = new CornerRadius(5), BorderThickness = new Thickness(1), Padding = new Thickness(7, 2, 7, 3), VerticalAlignment = VerticalAlignment.Center,
            Child = Text(keys, 11.5, "TextMuted", FontWeights.SemiBold) };
        return border.Ref(Border.BackgroundProperty, "SurfaceAlt").Ref(Border.BorderBrushProperty, "Stroke");
    }
    /// <summary>Rounded surface. The shadow lives on a sibling so text inside keeps ClearType rendering.</summary>
    public static FrameworkElement Card(UIElement child, Thickness padding, double radius = 12, bool shadow = true)
    {
        var card = new Border { Child = child, Padding = padding, CornerRadius = new CornerRadius(radius), BorderThickness = new Thickness(1) }
            .Ref(Border.BackgroundProperty, "Surface").Ref(Border.BorderBrushProperty, "Stroke");
        if (!shadow) return card;
        var grid = new Grid();
        var under = new Border { CornerRadius = new CornerRadius(radius), Margin = new Thickness(1) }.Ref(Border.BackgroundProperty, "Surface");
        under.Effect = new DropShadowEffect { BlurRadius = 16, ShadowDepth = 2, Direction = 270, Opacity = 0.07, Color = Colors.Black };
        grid.Children.Add(under); grid.Children.Add(card);
        return grid;
    }
    /// <summary>Gradient app mark drawn as vectors, matching Assets/YiQu.ico.</summary>
    public static Border Mark(double size)
    {
        var gradient = new LinearGradientBrush(Color.FromRgb(0x6A, 0x8B, 0xFF), Color.FromRgb(0x3A, 0x52, 0xE0), new Point(0.2, 0), new Point(0.8, 1)); gradient.Freeze();
        return new Border { Width = size, Height = size, CornerRadius = new CornerRadius(size * 0.26), Background = gradient,
            Child = new TextBlock { Text = "译", Foreground = Brushes.White, FontFamily = new FontFamily("Microsoft YaHei UI"), FontWeight = FontWeights.Bold, FontSize = size * 0.58, HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 0, size * 0.04) } };
    }

    static ImageSource? appIcon;
    public static ImageSource AppIcon => appIcon ??= LoadAppIcon();
    static ImageSource LoadAppIcon()
    {
        using var stream = IconStream();
        var decoder = new IconBitmapDecoder(stream, BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
        return decoder.Frames[0];
    }
    public static Stream IconStream() =>
        Assembly.GetExecutingAssembly().GetManifestResourceStream("YiQu.ico") ?? throw new InvalidOperationException("缺少内置图标资源");

    // Segoe Fluent Icons / MDL2 code points.
    public const string IconPin = "", IconPinned = "", IconHistory = "", IconSettings = "",
        IconPaste = "", IconCrop = "", IconScan = "", IconImage = "", IconCopy = "",
        IconSpeak = "", IconCheck = "", IconCancel = "", IconAdd = "", IconDelete = "",
        IconStar = "", IconStarFill = "", IconError = "", IconMin = "",
        IconMax = "", IconRestore = "", IconClose = "", IconTranslate = "",
        IconReuse = "", IconSend = "",
        IconClear = "\uEA99", IconStop = "\uE71A";
}
