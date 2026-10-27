using System;
using System.Collections.Generic;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;

namespace YiQu;

public sealed class HistoryWindow : ShellWindow
{
    readonly List<HistoryEntry> entries;
    readonly ListBox list = new() { Padding = new Thickness(6) };
    readonly StackPanel detail = new() { Margin = new Thickness(22, 4, 22, 22) };
    readonly TextBlock listEmpty = Theme.Text("", 12.5, "TextFaint").With(t => { t.HorizontalAlignment = HorizontalAlignment.Center; t.VerticalAlignment = VerticalAlignment.Center; t.TextAlignment = TextAlignment.Center; });
    readonly TextBlock meta = Theme.Text("", 12, "TextFaint").With(t => { t.VerticalAlignment = VerticalAlignment.Center; t.TextWrapping = TextWrapping.NoWrap; t.TextTrimming = TextTrimming.CharacterEllipsis; });
    readonly CheckBox favoritesOnly = new() { Content = Theme.IconText(Theme.IconStar, "仅看收藏", 12) };
    readonly TextBlock status = Theme.Text("", 12, "TextFaint").With(t => t.Margin = new Thickness(4, 10, 4, 0));
    readonly Button favorite, reuseButton, copyButton, deleteButton;
    readonly ToggleButton markdownToggle;
    readonly List<MarkdownText> texts = new();
    readonly Action<string> reuse;
    public HistoryWindow(Action<string> reuse, bool markdown, Action<bool> setMarkdown) : this(reuse, HistoryStore.Load(), markdown, setMarkdown) { }
    internal HistoryWindow(Action<string> reuse, List<HistoryEntry> initialEntries, bool markdown = false, Action<bool>? setMarkdown = null) : base("历史与收藏", dialog: true)
    {
        this.reuse = reuse; entries = initialEntries;
        // Shares its state with the result cards in the main window.
        markdownToggle = Theme.MarkdownToggle(markdown);
        markdownToggle.Click += (_, _) => {
            bool on = markdownToggle.IsChecked == true;
            foreach (var text in texts) text.Markdown = on;
            setMarkdown?.Invoke(on);
        };
        Title = "历史与收藏 · 译取"; Width = 920; Height = 620; MinWidth = 640; MinHeight = 420; WindowStartupLocation = WindowStartupLocation.CenterOwner;
        var root = new DockPanel { Margin = new Thickness(20, 6, 20, 14) }; Body = root;

        var top = new DockPanel { Margin = new Thickness(0, 0, 0, 12) }; DockPanel.SetDock(top, Dock.Top); root.Children.Add(top);
        var clear = Theme.TextButton("清空未收藏", (_, _) => Clear(), "DangerButton", Theme.IconDelete);
        DockPanel.SetDock(clear, Dock.Right); top.Children.Add(clear);
        favoritesOnly.Styled("Chip").With(c => c.HorizontalAlignment = HorizontalAlignment.Left);
        top.Children.Add(favoritesOnly); favoritesOnly.Checked += (_, _) => Refresh(); favoritesOnly.Unchecked += (_, _) => Refresh();
        DockPanel.SetDock(status, Dock.Bottom); root.Children.Add(status);

        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(290) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(14) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        root.Children.Add(grid);
        var listHost = new Grid(); listHost.Children.Add(list); listHost.Children.Add(listEmpty);
        grid.Children.Add(Theme.Card(listHost, new Thickness(0), 12, shadow: false));

        var detailPanel = new DockPanel();
        var actions = new DockPanel { Margin = new Thickness(22, 14, 14, 6) }; DockPanel.SetDock(actions, Dock.Top); detailPanel.Children.Add(actions);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal }; DockPanel.SetDock(buttons, Dock.Right); actions.Children.Add(buttons);
        favorite = Theme.IconButton(Theme.IconStar, "收藏", (_, _) => ToggleFavorite());
        reuseButton = Theme.TextButton("使用原文", (_, _) => { if (Selected is { } entry) { reuse(entry.Source); Close(); } }, "Ghost", Theme.IconReuse);
        copyButton = Theme.TextButton("复制译文", (_, _) => Copy(), "Ghost", Theme.IconCopy);
        deleteButton = Theme.IconButton(Theme.IconDelete, "删除", (_, _) => Delete());
        buttons.Children.Add(markdownToggle); buttons.Children.Add(favorite); buttons.Children.Add(reuseButton); buttons.Children.Add(copyButton); buttons.Children.Add(deleteButton);
        actions.Children.Add(meta);
        detailPanel.Children.Add(new ScrollViewer { Content = detail, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled });
        var detailCard = Theme.Card(detailPanel, new Thickness(0), 12, shadow: false);
        Grid.SetColumn(detailCard, 2); grid.Children.Add(detailCard);

        list.SelectionChanged += (_, _) => ShowDetail();
        Refresh();
    }
    HistoryEntry? Selected => (list.SelectedItem as ListBoxItem)?.Tag as HistoryEntry;
    void Refresh()
    {
        var selected = Selected; list.Items.Clear();
        foreach (var entry in entries.Where(e => favoritesOnly.IsChecked != true || e.Favorite).OrderByDescending(e => e.Time)) {
            var item = new ListBoxItem { Tag = entry, Content = ListRow(entry) };
            list.Items.Add(item); if (ReferenceEquals(selected, entry)) list.SelectedItem = item;
        }
        if (list.SelectedIndex < 0 && list.Items.Count > 0) list.SelectedIndex = 0;
        listEmpty.Text = entries.Count == 0 ? "暂无记录" : "暂无收藏";
        listEmpty.Visibility = list.Items.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        status.Text = $"{entries.Count} 条记录，{entries.Count(e => e.Favorite)} 条收藏";
        ShowDetail();
    }
    static UIElement ListRow(HistoryEntry entry)
    {
        var panel = new StackPanel();
        var line = new DockPanel();
        if (entry.Favorite) { var star = Theme.Glyph(Theme.IconStarFill, 11, "Star"); DockPanel.SetDock(star, Dock.Right); line.Children.Add(star); }
        line.Children.Add(Theme.Text(entry.Time.ToLocalTime().ToString("MM-dd HH:mm") + "  →  " + entry.Target, 11.5, "TextFaint").With(t => t.TextWrapping = TextWrapping.NoWrap));
        panel.Children.Add(line);
        var preview = entry.Source.Replace('\r', ' ').Replace('\n', ' ');
        if (preview.Length > 120) preview = preview[..120] + "…";
        panel.Children.Add(Theme.Text(preview, 13, "Text").With(t => { t.Margin = new Thickness(0, 4, 0, 0); t.MaxHeight = 40; t.TextTrimming = TextTrimming.CharacterEllipsis; }));
        return panel;
    }
    void ShowDetail()
    {
        var entry = Selected; detail.Children.Clear(); texts.Clear();
        foreach (var button in new Control[] { markdownToggle, favorite, reuseButton, copyButton, deleteButton }) button.IsEnabled = entry != null;
        if (entry == null) {
            meta.Text = "";
            detail.Children.Add(Theme.Text(entries.Count == 0 ? "暂无记录" : "选择一条记录", 13, "TextFaint").With(t => { t.HorizontalAlignment = HorizontalAlignment.Center; t.Margin = new Thickness(0, 120, 0, 0); }));
            return;
        }
        meta.Text = entry.Time.ToLocalTime().ToString("yyyy-MM-dd HH:mm") + " · 译为 " + entry.Target;
        favorite.Content = entry.Favorite ? Theme.IconStarFill : Theme.IconStar;
        if (entry.Favorite) favorite.Ref(ForegroundProperty, "Star"); else favorite.ClearValue(ForegroundProperty);
        favorite.ToolTip = entry.Favorite ? "取消收藏" : "收藏";
        detail.Children.Add(SectionLabel("原文"));
        bool markdown = markdownToggle.IsChecked == true;
        texts.Add(new MarkdownText(entry.Source, 14, markdown, "TextMuted"));
        detail.Children.Add(texts[^1]);
        foreach (var result in entry.Results) {
            bool failed = result.Error != null;
            var head = new StackPanel { Orientation = Orientation.Horizontal, Margin = new Thickness(0, 20, 0, 8) };
            head.Children.Add(failed ? Theme.Glyph(Theme.IconError, 12, "Danger") : Theme.ServiceDot(result.ServiceName));
            head.Children.Add(Theme.Text(result.ServiceName, 12.5, failed ? "Danger" : "TextMuted", FontWeights.SemiBold).With(t => t.Margin = new Thickness(8, 0, 0, 0)));
            detail.Children.Add(head);
            if (failed) { detail.Children.Add(MarkdownView.PassWheel(new TextBox { Text = result.Error!, FontSize = 15 }.Styled("ReadOnlyText").Ref(ForegroundProperty, "Danger"))); continue; }
            texts.Add(new MarkdownText(result.Text, 15, markdown));
            detail.Children.Add(texts[^1]);
        }
    }
    static UIElement SectionLabel(string text) => Theme.Text(text, 12.5, "TextFaint", FontWeights.SemiBold).With(t => t.Margin = new Thickness(0, 0, 0, 8));
    void Persist() { try { HistoryStore.Save(entries); Refresh(); } catch (Exception ex) { status.Text = "保存历史失败：" + ex.Message; } }
    void ToggleFavorite() { if (Selected is { } entry) { entry.Favorite = !entry.Favorite; Persist(); } }
    void Copy() { if (Selected is not { } entry) return; try { var text = string.Join("\n\n", entry.Results.Where(r => r.Error == null).Select(r => r.Text)); if (text.Length > 0) { Clipboard.SetText(text); status.Text = "已复制"; } } catch (Exception ex) { status.Text = "复制失败：" + ex.Message; } }
    void Delete() { if (Selected is { } entry && MessageBox.Show(this, "删除这条记录？", "删除记录", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes) { entries.Remove(entry); Persist(); } }
    void Clear() { var count = entries.Count(e => !e.Favorite); if (count == 0) return; if (MessageBox.Show(this, $"清空 {count} 条未收藏的记录？", "清空历史", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes) { entries.RemoveAll(e => !e.Favorite); Persist(); } }
}
