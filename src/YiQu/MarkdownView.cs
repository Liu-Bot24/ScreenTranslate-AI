using System;
using System.Diagnostics;
using System.Linq;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using Markdig;
using Markdig.Extensions.EmphasisExtras;
using Markdig.Extensions.Tables;
using Markdig.Extensions.TaskLists;
using Markdig.Syntax;
using Markdig.Syntax.Inlines;
using Block = System.Windows.Documents.Block;
using Inline = System.Windows.Documents.Inline;
using MdTable = Markdig.Extensions.Tables.Table;
using MdTableCell = Markdig.Extensions.Tables.TableCell;
using MdTableRow = Markdig.Extensions.Tables.TableRow;
using Table = System.Windows.Documents.Table;
using TableCell = System.Windows.Documents.TableCell;
using TableRow = System.Windows.Documents.TableRow;

namespace YiQu;

/// <summary>Renders Markdown (parsed by Markdig) into a themed FlowDocument for read-only display.</summary>
public static class MarkdownView
{
    // Single newlines stay line breaks, as in the plain-text view. Only "~~" is strikethrough, so "10~20" stays literal.
    static readonly MarkdownPipeline Pipeline = new MarkdownPipelineBuilder()
        .UsePipeTables().UseEmphasisExtras(EmphasisExtraOptions.Strikethrough).UseTaskLists().UseAutoLinks().UseSoftlineBreakAsHardlineBreak().Build();
    static readonly FontFamily Mono = new("Cascadia Mono, Consolas, Microsoft YaHei UI");

    public static RichTextBox Create(double fontSize) => new RichTextBox { FontSize = fontSize }.Styled("ReadOnlyRich");

    public static void Show(RichTextBox box, string markdown, string foreground = "Text") => box.Document = Render(markdown, box.FontSize, foreground);

    /// <summary>Text with Markdown syntax removed, for reading aloud.</summary>
    public static string PlainText(string markdown) => Markdown.ToPlainText(markdown, Pipeline);

    /// <summary>
    /// Maps a point in the rendered text back to the Markdown source by matching the visible characters
    /// in order; markup that is not rendered is skipped. Approximate where the source is ambiguous.
    /// </summary>
    public static int SourceOffset(string markdown, string renderedPrefix)
    {
        int offset = 0;
        foreach (char c in renderedPrefix) {
            if (char.IsWhiteSpace(c)) continue;
            int next = markdown.IndexOf(c, offset);
            if (next < 0) break;
            offset = next + 1;
        }
        // A point after a space or line break belongs before the next word, past any closing markup.
        if (renderedPrefix.Length > 0 && char.IsWhiteSpace(renderedPrefix[^1])) {
            while (offset < markdown.Length && !char.IsWhiteSpace(markdown[offset])) offset++;
            while (offset < markdown.Length && char.IsWhiteSpace(markdown[offset])) offset++;
        }
        return offset;
    }

    /// <summary>Passes wheel scrolling to the enclosing list; for text views that size to their content.</summary>
    public static T PassWheel<T>(T element) where T : UIElement
    {
        element.PreviewMouseWheel += (_, e) => {
            if (e.Handled || VisualTreeHelper.GetParent(element) is not UIElement parent) return;
            e.Handled = true;
            parent.RaiseEvent(new System.Windows.Input.MouseWheelEventArgs(e.MouseDevice, e.Timestamp, e.Delta) { RoutedEvent = UIElement.MouseWheelEvent, Source = element });
        };
        return element;
    }

    public static FlowDocument Render(string markdown, double fontSize, string foreground = "Text")
    {
        var document = new FlowDocument { PagePadding = new Thickness(0), FontSize = fontSize, FontFamily = Theme.UiFont, TextAlignment = TextAlignment.Left };
        document.SetResourceReference(FlowDocument.ForegroundProperty, foreground);
        AddBlocks(document.Blocks, Markdown.Parse(markdown, Pipeline), fontSize);
        if (document.Blocks.FirstBlock is { } first) first.Margin = new Thickness(first.Margin.Left, 0, first.Margin.Right, first.Margin.Bottom);
        TrimLast(document.Blocks);
        return document;
    }

    static double Gap(double size) => Math.Round(size * 0.6);
    static void TrimLast(BlockCollection blocks)
    {
        if (blocks.LastBlock is { } last) last.Margin = new Thickness(last.Margin.Left, last.Margin.Top, last.Margin.Right, 0);
    }
    static void AddBlocks(BlockCollection target, ContainerBlock source, double size)
    {
        foreach (var block in source)
            if (RenderBlock(block, size) is { } rendered) target.Add(rendered);
    }
    static Block? RenderBlock(Markdig.Syntax.Block block, double size)
    {
        switch (block) {
            case HeadingBlock heading: {
                var paragraph = Paragraph(heading.Inline, size);
                paragraph.FontSize = size * (heading.Level switch { 1 => 1.45, 2 => 1.3, 3 => 1.15, _ => 1.0 });
                paragraph.FontWeight = FontWeights.SemiBold;
                paragraph.Margin = new Thickness(0, Gap(size), 0, Math.Round(size * 0.4));
                return paragraph;
            }
            case ParagraphBlock paragraph: return Paragraph(paragraph.Inline, size);
            case CodeBlock code: {
                var paragraph = new Paragraph { FontFamily = Mono, FontSize = Math.Round(size * 0.86, 1), Padding = new Thickness(12, 8, 12, 8), Margin = new Thickness(0, 0, 0, Gap(size)) };
                paragraph.SetResourceReference(TextElement.BackgroundProperty, "SurfaceAlt");
                for (int i = 0; i < code.Lines.Count; i++) {
                    if (i > 0) paragraph.Inlines.Add(new LineBreak());
                    paragraph.Inlines.Add(new Run(code.Lines.Lines[i].Slice.ToString()));
                }
                return paragraph;
            }
            case QuoteBlock quote: {
                var section = new Section { Padding = new Thickness(12, 0, 0, 0), BorderThickness = new Thickness(3, 0, 0, 0), Margin = new Thickness(0, 0, 0, Gap(size)) };
                section.SetResourceReference(Block.BorderBrushProperty, "StrokeStrong");
                section.SetResourceReference(TextElement.ForegroundProperty, "TextMuted");
                AddBlocks(section.Blocks, quote, size); TrimLast(section.Blocks);
                return section;
            }
            case ListBlock list: {
                var rendered = new List { MarkerStyle = list.IsOrdered ? TextMarkerStyle.Decimal : TextMarkerStyle.Disc, Padding = new Thickness(Math.Round(size * 1.4), 0, 0, 0), Margin = new Thickness(0, 0, 0, Gap(size)) };
                if (list.IsOrdered && int.TryParse(list.OrderedStart, out int start) && start > 0) rendered.StartIndex = start;
                foreach (var item in list.OfType<ListItemBlock>()) {
                    var listItem = new ListItem();
                    AddBlocks(listItem.Blocks, item, size);
                    // Tight lists keep items close; nested lists sit directly under their item.
                    foreach (var child in listItem.Blocks) child.Margin = new Thickness(0, 0, 0, list.IsLoose && child is Paragraph ? Gap(size) : Math.Round(size * 0.2));
                    rendered.ListItems.Add(listItem);
                }
                if (rendered.ListItems.LastListItem?.Blocks.LastBlock is { } last) last.Margin = new Thickness(0);
                return rendered;
            }
            case ThematicBreakBlock: {
                var rule = new Paragraph { FontSize = 1, BorderThickness = new Thickness(0, 0, 0, 1), Margin = new Thickness(0, Math.Round(size * 0.3), 0, Gap(size)) };
                rule.SetResourceReference(Block.BorderBrushProperty, "Stroke");
                return rule;
            }
            case MdTable table: return Table(table, size);
            case LinkReferenceDefinitionGroup: return null;
            case LeafBlock leaf when leaf.Inline != null: return Paragraph(leaf.Inline, size);
            case LeafBlock leaf: {
                // HTML blocks and other raw leaves are shown as written.
                var paragraph = new Paragraph { Margin = new Thickness(0, 0, 0, Gap(size)) };
                for (int i = 0; i < leaf.Lines.Count; i++) {
                    if (i > 0) paragraph.Inlines.Add(new LineBreak());
                    paragraph.Inlines.Add(new Run(leaf.Lines.Lines[i].Slice.ToString()));
                }
                return paragraph;
            }
            case ContainerBlock container: {
                var section = new Section();
                AddBlocks(section.Blocks, container, size);
                return section;
            }
        }
        return null;
    }
    static Table Table(MdTable source, double size)
    {
        var table = new Table { CellSpacing = 0, BorderThickness = new Thickness(1, 1, 0, 0), Margin = new Thickness(0, 0, 0, Gap(size)) };
        table.SetResourceReference(Block.BorderBrushProperty, "Stroke");
        var rows = source.OfType<MdTableRow>().ToList();
        int columns = Math.Max(source.ColumnDefinitions.Count, rows.Select(r => r.OfType<MdTableCell>().Sum(c => Math.Max(1, c.ColumnSpan))).DefaultIfEmpty(1).Max());
        for (int i = 0; i < columns; i++) table.Columns.Add(new TableColumn { Width = new GridLength(1, GridUnitType.Star) });
        var group = new TableRowGroup();
        table.RowGroups.Add(group);
        foreach (var row in rows) {
            var renderedRow = new TableRow();
            if (row.IsHeader) {
                renderedRow.FontWeight = FontWeights.SemiBold;
                renderedRow.SetResourceReference(TextElement.BackgroundProperty, "SurfaceAlt");
            }
            int column = 0;
            foreach (var cell in row.OfType<MdTableCell>()) {
                var renderedCell = new TableCell { Padding = new Thickness(10, 5, 10, 5), BorderThickness = new Thickness(0, 0, 1, 1), ColumnSpan = Math.Max(1, cell.ColumnSpan) };
                renderedCell.SetResourceReference(TableCell.BorderBrushProperty, "Stroke");
                AddBlocks(renderedCell.Blocks, cell, size);
                var alignment = column < source.ColumnDefinitions.Count ? source.ColumnDefinitions[column].Alignment : null;
                column += renderedCell.ColumnSpan;
                foreach (var child in renderedCell.Blocks) {
                    child.Margin = new Thickness(0);
                    child.TextAlignment = alignment switch { TableColumnAlign.Center => TextAlignment.Center, TableColumnAlign.Right => TextAlignment.Right, _ => TextAlignment.Left };
                }
                renderedRow.Cells.Add(renderedCell);
            }
            group.Rows.Add(renderedRow);
        }
        return table;
    }
    static Paragraph Paragraph(ContainerInline? inline, double size)
    {
        var paragraph = new Paragraph { Margin = new Thickness(0, 0, 0, Gap(size)) };
        if (inline != null) AddInlines(paragraph.Inlines, inline);
        return paragraph;
    }
    static void AddInlines(InlineCollection target, ContainerInline source)
    {
        foreach (var inline in source)
            if (RenderInline(inline) is { } rendered) target.Add(rendered);
    }
    static Inline? RenderInline(Markdig.Syntax.Inlines.Inline inline)
    {
        switch (inline) {
            case LiteralInline literal: return new Run(literal.Content.ToString());
            case CodeInline code: {
                var run = new Run(code.Content) { FontFamily = Mono };
                run.SetResourceReference(TextElement.BackgroundProperty, "SurfaceAlt");
                return run;
            }
            case LineBreakInline lineBreak: return lineBreak.IsHard ? new LineBreak() : new Run(" ");
            case TaskList task: return new Run(task.Checked ? "☑ " : "☐ ");
            case HtmlEntityInline entity: return new Run(entity.Transcoded.ToString());
            case HtmlInline html: return new Run(html.Tag);
            case AutolinkInline auto: return Link(auto.IsEmail ? "mailto:" + auto.Url : auto.Url, new Run(auto.Url));
            case LinkInline link: {
                var content = new Span();
                AddInlines(content.Inlines, link);
                // Images cannot be fetched here; their alt text stands in.
                return link.IsImage ? content : Link(link.GetDynamicUrl?.Invoke() ?? link.Url, content);
            }
            case EmphasisInline emphasis: {
                Span span = emphasis.DelimiterChar switch {
                    '~' => new Span { TextDecorations = System.Windows.TextDecorations.Strikethrough },
                    _ when emphasis.DelimiterCount >= 2 => new Bold(),
                    _ => new Italic()
                };
                AddInlines(span.Inlines, emphasis);
                return span;
            }
            case ContainerInline container: {
                var span = new Span();
                AddInlines(span.Inlines, container);
                return span;
            }
        }
        return null;
    }
    static Inline Link(string? url, Inline content)
    {
        if (!Uri.TryCreate(url, UriKind.Absolute, out var uri) || uri.Scheme is not ("http" or "https" or "mailto")) return content;
        var link = new Hyperlink(content) { NavigateUri = uri, ToolTip = uri.OriginalString };
        link.SetResourceReference(TextElement.ForegroundProperty, "AccentText");
        link.RequestNavigate += (_, e) => {
            e.Handled = true;
            try { Process.Start(new ProcessStartInfo(e.Uri.AbsoluteUri) { UseShellExecute = true }); }
            catch (Exception ex) when (ex is System.ComponentModel.Win32Exception or InvalidOperationException) { MessageBox.Show("无法打开链接：" + ex.Message, "译取"); }
        };
        return link;
    }
}

/// <summary>Read-only text shown either as selectable plain text or as rendered Markdown (built on first use).</summary>
public sealed class MarkdownText : Grid
{
    readonly string text, foreground;
    readonly double fontSize;
    readonly TextBox raw;
    RichTextBox? rendered;

    public MarkdownText(string text, double fontSize, bool markdown, string foreground = "Text")
    {
        this.text = text; this.fontSize = fontSize; this.foreground = foreground;
        raw = MarkdownView.PassWheel(new TextBox { Text = text, FontSize = fontSize }.Styled("ReadOnlyText").Ref(Control.ForegroundProperty, foreground));
        Children.Add(raw);
        Markdown = markdown;
    }
    public bool Markdown
    {
        get => rendered?.Visibility == Visibility.Visible;
        set {
            if (value && rendered == null) {
                rendered = MarkdownView.PassWheel(MarkdownView.Create(fontSize));
                MarkdownView.Show(rendered, text, foreground);
                Children.Add(rendered);
            }
            raw.Visibility = value ? Visibility.Collapsed : Visibility.Visible;
            if (rendered != null) rendered.Visibility = value ? Visibility.Visible : Visibility.Collapsed;
        }
    }
}
