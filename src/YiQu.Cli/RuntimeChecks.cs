using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using YiQu;

// Checks the RapidOCR component installer: hash and archive safety, cancellation, real download,
// verification, reuse, and recognition through the app's worker. Downloads about 128 MB on first run.
internal static class RuntimeChecks
{
    sealed class Progress(Action<RuntimeProgress> callback) : IProgress<RuntimeProgress>
    { public void Report(RuntimeProgress value) => callback(value); }
    static void Check(bool value, string name) { if (!value) throw new Exception(name); Console.WriteLine("PASS " + name); }

    public static int Run(string? root)
    {
        var image = TestImages.Png(); // Rendered on the STA thread before any await.
        Verify(Path.GetFullPath(root ?? RapidOcrRuntime.Root), image).GetAwaiter().GetResult();
        return 0;
    }

    static async Task Verify(string root, byte[] image)
    {
        string test = Path.Combine(Path.GetTempPath(), "YiQu-runtime-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(test);
        var data = Encoding.UTF8.GetBytes("runtime checksum fixture");
        string file = Path.Combine(test, "hash.bin"); await File.WriteAllBytesAsync(file, data);
        string hash = Convert.ToHexString(SHA256.HashData(data));
        Check(await RapidOcrRuntime.ValidFileAsync(file, hash, "SHA256", data.Length, CancellationToken.None), "expected component hash accepted");
        data[0] ^= 1; await File.WriteAllBytesAsync(file, data);
        Check(!await RapidOcrRuntime.ValidFileAsync(file, hash, "SHA256", data.Length, CancellationToken.None), "corrupted component rejected");

        string archive = Path.Combine(test, "traversal.zip");
        using (var zip = ZipFile.Open(archive, ZipArchiveMode.Create)) {
            using var writer = new StreamWriter(zip.CreateEntry("../escaped.txt").Open()); writer.Write("fixture");
        }
        bool rejected = false;
        try { RapidOcrRuntime.Extract(archive, Path.Combine(test, "unpack"), false, CancellationToken.None); }
        catch (InvalidDataException) { rejected = true; }
        Check(rejected && !File.Exists(Path.Combine(test, "escaped.txt")), "archive traversal rejected before extraction");

        using (var cancelled = new CancellationTokenSource()) {
            cancelled.Cancel(); rejected = false;
            try { await RapidOcrRuntime.InstallAsync(null, cancelled.Token, Path.Combine(test, "pre-cancel")); }
            catch (OperationCanceledException) { rejected = true; }
            Check(rejected && !Directory.Exists(Path.Combine(test, "pre-cancel")), "pre-cancelled installation leaves no runtime");
        }
        if (RapidOcrRuntime.InstalledPython(root) == null) {
            using var cancel = new CancellationTokenSource(); rejected = false;
            try { await RapidOcrRuntime.InstallAsync(new Progress(p => { if (p.Percent > 0) cancel.Cancel(); }), cancel.Token, root); }
            catch (OperationCanceledException) { rejected = true; }
            Check(rejected && RapidOcrRuntime.InstalledPython(root) == null && Directory.GetDirectories(root, ".install-*").Length == 0,
                "download cancellation publishes no runtime and removes partial installation");
        }

        string last = "";
        var progress = new Progress(p => { string next = p.Message.Split('·')[0].Trim(); if (next != last) { Console.WriteLine(next); last = next; } });
        string python = await RapidOcrRuntime.InstallAsync(progress, CancellationToken.None, root);
        Check(File.Exists(python) && python == RapidOcrRuntime.InstalledPython(root), "downloaded Python, dependencies and models pass real inference verification");
        Check(await RapidOcrRuntime.InstallAsync(progress, CancellationToken.None, root) == python, "ready runtime is reused without reinstalling");
        try {
            var result = await OcrEngine.RecognizeAsync(image, new OcrSettings { Provider = "rapidocr", LocalPythonPath = python }, CancellationToken.None);
            // RapidOCR may return words of a short line as separate lines.
            Check(string.Join(" ", result.Text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries)).Contains(TestImages.Sample, StringComparison.OrdinalIgnoreCase),
                "downloaded runtime recognizes a generated image through the app worker");
        } finally { OcrEngine.Shutdown(); }
        Directory.Delete(test, true);
    }
}
