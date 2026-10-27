using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Shell;

namespace YiQu;

/// <summary>
/// Window with the themed custom title bar. Native resize, snap, Alt+Space and caption double-click
/// stay with Windows through WindowChrome; subclasses put their content in <see cref="Body"/>.
/// </summary>
public class ShellWindow : Window
{
    const double TitleHeight = 44;
    protected readonly Grid Root = new();
    protected readonly StackPanel TitleActions = new() { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 6, 0) };
    readonly Button? maximize;

    protected ShellWindow(string title, bool dialog)
    {
        Title = title;
        FontFamily = Theme.UiFont; FontSize = 13;
        UseLayoutRounding = true; SnapsToDevicePixels = true;
        Icon = Theme.AppIcon;
        Theme.Attach(this); Theme.Attach(Root);
        this.Ref(BackgroundProperty, "Bg").Ref(ForegroundProperty, "Text");
        Root.Ref(Panel.BackgroundProperty, "Bg");
        TextOptions.SetTextFormattingMode(Root, TextFormattingMode.Display);
        WindowChrome.SetWindowChrome(this, new WindowChrome {
            CaptionHeight = TitleHeight, ResizeBorderThickness = new Thickness(6),
            GlassFrameThickness = new Thickness(0, 0, 0, 1), CornerRadius = new CornerRadius(0), UseAeroCaptionButtons = false
        });
        Root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(TitleHeight) });
        Root.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });

        var bar = new DockPanel { LastChildFill = true };
        var captions = new StackPanel { Orientation = Orientation.Horizontal };
        WindowChrome.SetIsHitTestVisibleInChrome(captions, true);
        WindowChrome.SetIsHitTestVisibleInChrome(TitleActions, true);
        DockPanel.SetDock(captions, Dock.Right); bar.Children.Add(captions);
        DockPanel.SetDock(TitleActions, Dock.Right); bar.Children.Add(TitleActions);
        if (!dialog) {
            captions.Children.Add(Caption(Theme.IconMin, "最小化", "Caption", () => SystemCommands.MinimizeWindow(this)));
            maximize = Caption(Theme.IconMax, "最大化", "Caption", () => { if (WindowState == WindowState.Maximized) SystemCommands.RestoreWindow(this); else SystemCommands.MaximizeWindow(this); });
            captions.Children.Add(maximize);
        }
        captions.Children.Add(Caption(Theme.IconClose, "关闭", "CaptionClose", Close));
        var heading = new StackPanel { Orientation = Orientation.Horizontal, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(16, 0, 0, 0) };
        heading.Children.Add(Theme.Mark(20));
        heading.Children.Add(Theme.Text(title, 13, "Text", FontWeights.SemiBold).With(t => { t.Margin = new Thickness(10, 0, 0, 1); t.VerticalAlignment = VerticalAlignment.Center; t.TextWrapping = TextWrapping.NoWrap; }));
        bar.Children.Add(heading);
        Root.Children.Add(bar);
        Content = Root;

        StateChanged += (_, _) => UpdateMaximized();
        SourceInitialized += (_, _) => ApplyFrame();
        Theme.Changed += ApplyFrame;
        Closed += (_, _) => Theme.Changed -= ApplyFrame;
    }

    protected UIElement Body { set { Grid.SetRow(value, 1); Root.Children.Add(value); } }
    /// <summary>Title bar controls stay mouse-only, like the caption buttons, so global Alt hotkeys never leave a focus ring there.</summary>
    protected void AddTitleAction(Control control) { control.Focusable = false; TitleActions.Children.Add(control); }

    Button Caption(string glyph, string tip, string style, Action action)
    {
        var button = new Button { Content = glyph, ToolTip = tip, Height = TitleHeight }.Styled(style);
        button.Click += (_, _) => action();
        return button;
    }
    void UpdateMaximized()
    {
        bool max = WindowState == WindowState.Maximized;
        // A maximized WindowChrome window extends past the work area by the resize frame; inset the content.
        Root.Margin = max ? MaximizedInset() : new Thickness(0);
        if (maximize != null) { maximize.Content = max ? Theme.IconRestore : Theme.IconMax; maximize.ToolTip = max ? "还原" : "最大化"; }
    }
    Thickness MaximizedInset()
    {
        var frame = SystemParameters.WindowResizeBorderThickness;
        double padded = GetSystemMetrics(92) / VisualTreeHelper.GetDpi(this).DpiScaleX;
        return new Thickness(frame.Left + padded, frame.Top + padded, frame.Right + padded, frame.Bottom + padded);
    }
    void ApplyFrame()
    {
        var hwnd = new WindowInteropHelper(this).Handle;
        if (hwnd == IntPtr.Zero) return;
        // Cosmetic only: rounded corners and a border matching the palette on Windows 11.
        // Older Windows versions return an error HRESULT and keep their default frame.
        int round = 2, dark = Theme.IsDark ? 1 : 0;
        DwmSetWindowAttribute(hwnd, 33, ref round, sizeof(int));
        DwmSetWindowAttribute(hwnd, 20, ref dark, sizeof(int));
    }
    [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("user32.dll")] static extern int GetSystemMetrics(int index);
}
