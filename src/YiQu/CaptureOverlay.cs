using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Forms = System.Windows.Forms;

namespace YiQu;

public sealed class CaptureOverlay : Forms.Form
{
    private readonly Bitmap desktop;
    private readonly Rectangle desktopBounds;
    private readonly TaskCompletionSource<byte[]?> completion = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private Point? anchor;
    private Rectangle selection;
    private byte[]? result;

    private CaptureOverlay(Bitmap desktop, Rectangle bounds)
    {
        this.desktop = desktop; desktopBounds = bounds;
        AutoScaleMode = Forms.AutoScaleMode.None;
        FormBorderStyle = Forms.FormBorderStyle.None;
        StartPosition = Forms.FormStartPosition.Manual;
        Bounds = bounds; TopMost = true; ShowInTaskbar = false;
        DoubleBuffered = true; KeyPreview = true;
        Cursor = Forms.Cursors.Cross;
        Text = "截图";
        Shown += (_, _) => {
            // Use physical screen coordinates; supports monitors to the left/above the primary monitor.
            SetWindowPos(Handle, new IntPtr(-1), bounds.X, bounds.Y, bounds.Width, bounds.Height, 0x40);
            Activate();
        };
        MouseDown += (_, e) => {
            if (e.Button == Forms.MouseButtons.Right) { Close(); return; }
            if (e.Button != Forms.MouseButtons.Left) return;
            anchor = CursorPoint(); Capture = true;
        };
        MouseMove += (_, _) => {
            // Before dragging only the hint pill follows the cursor; repaint just its old and new area.
            if (anchor is null) { var old = hintArea; hintArea = HintArea(CursorPoint()); Invalidate(Rectangle.Union(old, hintArea)); return; }
            var point = CursorPoint();
            selection = Rectangle.Intersect(new Rectangle(Math.Min(point.X, anchor.Value.X),
                Math.Min(point.Y, anchor.Value.Y), Math.Abs(point.X-anchor.Value.X), Math.Abs(point.Y-anchor.Value.Y)),
                new Rectangle(Point.Empty, desktop.Size));
            Invalidate();
        };
        MouseUp += (_, e) => {
            if (e.Button != Forms.MouseButtons.Left || anchor is null) return;
            Capture = false;
            if (selection.Width < 3 || selection.Height < 3) { anchor = null; selection = Rectangle.Empty; Invalidate(); return; }
            try
            {
                using var crop = desktop.Clone(selection, PixelFormat.Format32bppArgb);
                using var stream = new MemoryStream();
                crop.Save(stream, ImageFormat.Png); result = stream.ToArray();
            }
            catch (Exception ex) { completion.TrySetException(ex); }
            Close();
        };
        KeyDown += (_, e) => { if (e.KeyCode == Forms.Keys.Escape) { e.Handled = true; Close(); } };
        FormClosed += (_, _) => { completion.TrySetResult(result); Dispose(); };
    }

    public static Task<byte[]?> CaptureAsync()
    {
        var bounds = Forms.SystemInformation.VirtualScreen;
        var desktop = new Bitmap(bounds.Width, bounds.Height, PixelFormat.Format32bppArgb);
        try
        {
            using (var graphics = Graphics.FromImage(desktop))
                graphics.CopyFromScreen(bounds.Location, Point.Empty, bounds.Size, CopyPixelOperation.SourceCopy);
            var overlay = new CaptureOverlay(desktop, bounds);
            overlay.Show();
            return overlay.completion.Task;
        }
        catch { desktop.Dispose(); throw; }
    }

    private Point CursorPoint()
    {
        GetCursorPos(out var point);
        return new Point(Math.Clamp(point.X - desktopBounds.X, 0, desktop.Width),
            Math.Clamp(point.Y - desktopBounds.Y, 0, desktop.Height));
    }
    protected override void OnPaint(Forms.PaintEventArgs e)
    {
        var g = e.Graphics;
        g.DrawImageUnscaled(desktop, 0, 0);
        using var shade = new SolidBrush(Color.FromArgb(120, 8, 10, 18));
        using var region = new Region(new Rectangle(Point.Empty, desktop.Size));
        if (!selection.IsEmpty) region.Exclude(selection);
        g.FillRegion(shade, region);
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
        var point = CursorPoint();
        if (!selection.IsEmpty)
        {
            using var border = new Pen(Accent, 1.5f);
            g.DrawRectangle(border, selection);
            // Corner handles.
            using var fill = new SolidBrush(Color.White);
            using var outline = new Pen(Accent, 1.5f);
            foreach (var c in new[] { new Point(selection.Left, selection.Top), new Point(selection.Right, selection.Top), new Point(selection.Left, selection.Bottom), new Point(selection.Right, selection.Bottom) })
            {
                var handle = new Rectangle(c.X - 4, c.Y - 4, 8, 8);
                g.FillEllipse(fill, handle); g.DrawEllipse(outline, handle);
            }
            var size = $"{selection.Width} × {selection.Height}";
            var measured = g.MeasureString(size, font);
            int above = selection.Top - (int)measured.Height - 16;
            Pill(g, size, font, new Point(selection.Left, above >= 0 ? above : selection.Top + 8), measured);
        }
        else
        {
            hintArea = HintArea(point);
            Pill(g, Hint, font, hintArea.Location, g.MeasureString(Hint, font));
        }
    }
    const string Hint = "拖动选择区域 · Esc 取消";
    static readonly Color Accent = Color.FromArgb(92, 130, 255);
    readonly Font font = new("Microsoft YaHei UI", 10.5f);
    Rectangle hintArea;
    Rectangle HintArea(Point cursor)
    {
        var measured = Forms.TextRenderer.MeasureText(Hint, font);
        int width = measured.Width + 40, height = measured.Height + 20;
        return new Rectangle(Math.Max(10, Math.Min(cursor.X + 18, desktop.Width - width - 10)), Math.Max(10, Math.Min(cursor.Y + 22, desktop.Height - height - 10)), width, height);
    }
    static void Pill(Graphics g, string text, Font font, Point at, SizeF measured)
    {
        var box = new RectangleF(at.X, at.Y, measured.Width + 20, measured.Height + 8);
        using var path = new GraphicsPath();
        float d = box.Height;
        path.AddArc(box.X, box.Y, d, d, 90, 180); path.AddArc(box.Right - d, box.Y, d, d, 270, 180); path.CloseFigure();
        using var back = new SolidBrush(Color.FromArgb(225, 24, 26, 32));
        g.FillPath(back, path);
        using var brush = new SolidBrush(Color.White);
        g.DrawString(text, font, brush, box.X + 10, box.Y + 4);
    }
    protected override void Dispose(bool disposing) { if (disposing) { desktop.Dispose(); font.Dispose(); } base.Dispose(disposing); }
    [StructLayout(LayoutKind.Sequential)] private struct POINT { public int X, Y; }
    [DllImport("user32.dll")] private static extern bool GetCursorPos(out POINT point);
    [DllImport("user32.dll")] private static extern bool SetWindowPos(IntPtr hwnd, IntPtr after, int x, int y, int width, int height, uint flags);
}
