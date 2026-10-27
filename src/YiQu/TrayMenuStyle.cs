using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using Forms = System.Windows.Forms;

namespace YiQu;

/// <summary>Flat, rounded tray menu matching the WPF palette (WinForms ContextMenuStrip).</summary>
static class TrayMenuStyle
{
    public static void Apply(Forms.ContextMenuStrip menu)
    {
        menu.Renderer = new Renderer();
        menu.Font = new Font("Microsoft YaHei UI", 9.5f);
        menu.ShowImageMargin = false;
        menu.Padding = new Forms.Padding(4, 6, 4, 6);
        menu.BackColor = Palette.Back;
        menu.ForeColor = Palette.Text;
    }
    public static Forms.ToolStripMenuItem Item(string text, string? shortcut, Action action)
    {
        var item = new Forms.ToolStripMenuItem(text) { ShortcutKeyDisplayString = shortcut, Padding = new Forms.Padding(6, 7, 6, 7), ForeColor = Palette.Text };
        item.Click += (_, _) => action();
        return item;
    }

    static class Palette
    {
        static Color C(uint light, uint dark) { var c = Theme.Rgb(Theme.IsDark ? dark : light); return Color.FromArgb(c.R, c.G, c.B); }
        public static Color Back => C(0xFFFFFF, 0x26272D);
        public static Color Hover => C(0xEEF1F5, 0x34363E);
        public static Color Border => C(0xDDE1E7, 0x3D4049);
        public static Color Text => C(0x191C22, 0xECEDF1);
        public static Color Faint => C(0x8C93A0, 0x8A909B);
    }

    sealed class Renderer : Forms.ToolStripProfessionalRenderer
    {
        public Renderer() : base(new Forms.ProfessionalColorTable()) { RoundedEdges = false; }
        protected override void OnRenderToolStripBackground(Forms.ToolStripRenderEventArgs e) { using var b = new SolidBrush(Palette.Back); e.Graphics.FillRectangle(b, e.AffectedBounds); }
        protected override void OnRenderToolStripBorder(Forms.ToolStripRenderEventArgs e)
        {
            using var pen = new Pen(Palette.Border);
            e.Graphics.DrawRectangle(pen, 0, 0, e.ToolStrip.Width - 1, e.ToolStrip.Height - 1);
        }
        protected override void OnRenderMenuItemBackground(Forms.ToolStripItemRenderEventArgs e)
        {
            if (!e.Item.Selected || !e.Item.Enabled) return;
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            var r = new Rectangle(2, 1, e.Item.Width - 4, e.Item.Height - 2);
            using var path = Rounded(r, 5);
            using var b = new SolidBrush(Palette.Hover);
            e.Graphics.FillPath(b, path);
        }
        protected override void OnRenderItemText(Forms.ToolStripItemTextRenderEventArgs e)
        {
            // Shortcut text is drawn through this hook as well; give it the faint color.
            e.TextColor = e.Text == (e.Item as Forms.ToolStripMenuItem)?.ShortcutKeyDisplayString ? Palette.Faint : Palette.Text;
            base.OnRenderItemText(e);
        }
        protected override void OnRenderSeparator(Forms.ToolStripSeparatorRenderEventArgs e)
        {
            using var pen = new Pen(Palette.Border);
            int y = e.Item.Height / 2;
            e.Graphics.DrawLine(pen, 8, y, e.Item.Width - 8, y);
        }
        static GraphicsPath Rounded(Rectangle r, int radius)
        {
            var path = new GraphicsPath(); int d = radius * 2;
            path.AddArc(r.X, r.Y, d, d, 180, 90); path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90); path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            path.CloseFigure(); return path;
        }
    }
}
