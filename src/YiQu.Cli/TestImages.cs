using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

/// <summary>Generates OCR test images so the checks never depend on personal screenshots.</summary>
internal static class TestImages
{
    public const string Sample = "Windows OCR and local models";

    /// <summary>Black text on white as a frozen bitmap. Call on an STA thread.</summary>
    public static BitmapSource Text(string text = Sample)
    {
        var formatted = new FormattedText(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight, new Typeface("Segoe UI"), 28, Brushes.Black, 1.0);
        int width = (int)Math.Ceiling(formatted.Width) + 48, height = (int)Math.Ceiling(formatted.Height) + 48;
        var visual = new DrawingVisual();
        using (var drawing = visual.RenderOpen()) {
            drawing.DrawRectangle(Brushes.White, null, new Rect(0, 0, width, height));
            drawing.DrawText(formatted, new Point(24, 24));
        }
        var bitmap = new RenderTargetBitmap(width, height, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(visual);
        bitmap.Freeze();
        return bitmap;
    }

    public static byte[] Png(string text = Sample)
    {
        var encoder = new PngBitmapEncoder(); encoder.Frames.Add(BitmapFrame.Create(Text(text)));
        using var stream = new MemoryStream(); encoder.Save(stream);
        return stream.ToArray();
    }
}
