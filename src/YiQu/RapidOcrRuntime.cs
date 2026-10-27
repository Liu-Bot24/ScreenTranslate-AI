using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace YiQu;

public sealed record RuntimeProgress(string Message, double? Percent = null);

// Downloads only a reviewed, hash-pinned Windows x64 runtime. Installation is private to
// the user and becomes discoverable only after the complete OCR inference check succeeds.
public static class RapidOcrRuntime
{
    sealed record Asset(string Name, string Url, string Hash, string Algorithm, long Size, string Kind, string Target);
    sealed record Manifest(string Id, Asset[] Files);
    sealed record Installed(string Id, string Directory);
    static readonly JsonSerializerOptions Json = new() { PropertyNameCaseInsensitive = true };
    static readonly Manifest Bundle = LoadManifest();
    static readonly HttpClient Client = CreateClient();
    static HttpClient CreateClient()
    {
        var client = new HttpClient { Timeout = Timeout.InfiniteTimeSpan };
        // The official model CDN rejects requests with an empty User-Agent.
        client.DefaultRequestHeaders.UserAgent.ParseAdd("YiQu/1.0");
        return client;
    }
    public static string Root => Path.Combine(SettingsStore.DirectoryPath, "ocr");
    public static long DownloadBytes { get { long size = 0; foreach (var f in Bundle.Files) size += f.Size; return size; } }
    static Manifest LoadManifest()
    {
        using var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("YiQu.rapidocr-runtime.json")!;
        return JsonSerializer.Deserialize<Manifest>(stream, Json)!;
    }
    public static string? InstalledPython(string? root = null)
    {
        root ??= Root;
        try {
            var record = JsonSerializer.Deserialize<Installed>(File.ReadAllText(Path.Combine(root, "current.json")), Json);
            if (record == null || record.Id != Bundle.Id || record.Directory != Path.GetFileName(record.Directory) || !record.Directory.StartsWith(Bundle.Id + "-", StringComparison.Ordinal)) return null;
            var directory = Path.Combine(root, record.Directory);
            var python = Path.Combine(directory, "tools", "python.exe");
            return File.Exists(python) && File.Exists(Path.Combine(directory, "ready.json")) ? python : null;
        } catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException or ArgumentException) { return null; }
    }
    public static async Task<string> InstallAsync(IProgress<RuntimeProgress>? progress, CancellationToken token, string? root = null)
    {
        if (!Environment.Is64BitOperatingSystem) throw new InvalidOperationException("RapidOCR 需要 64 位 Windows");
        token.ThrowIfCancellationRequested();
        root = Path.GetFullPath(root ?? Root); Directory.CreateDirectory(root);
        FileStream installLock;
        try { installLock = new FileStream(Path.Combine(root, "install.lock"), FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None); }
        catch (IOException) { throw new InvalidOperationException("RapidOCR 正在安装，请稍后再试"); }
        using var heldLock = installLock;
        string? existing = InstalledPython(root);
        if (existing != null) {
            progress?.Report(new("正在检查已安装组件…"));
            try { await VerifyAsync(existing, token).ConfigureAwait(false); return existing; }
            catch (Exception ex) when (ex is InvalidOperationException or IOException or JsonException or System.ComponentModel.Win32Exception or TimeoutException) {
                progress?.Report(new("组件需要修复，正在重新准备…"));
            }
        }
        string name = Bundle.Id + "-" + Guid.NewGuid().ToString("N");
        string staging = Path.Combine(root, ".install-" + Guid.NewGuid().ToString("N"));
        string final = Path.Combine(root, name);
        Directory.CreateDirectory(staging);
        string cache = Path.Combine(root, "downloads"); Directory.CreateDirectory(cache);
        bool published = false;
        try {
            long completed = 0;
            foreach (var asset in Bundle.Files) {
                token.ThrowIfCancellationRequested();
                string archive = Path.Combine(cache, asset.Hash + ".download");
                await DownloadAsync(asset, archive, completed, progress, token).ConfigureAwait(false);
                progress?.Report(new("正在准备识别组件…", completed * 100.0 / DownloadBytes));
                if (asset.Kind == "model") {
                    string destination = SafePath(staging, asset.Target);
                    Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                    File.Copy(archive, destination, true);
                } else {
                    await Task.Run(() => Extract(archive, SafePath(staging, asset.Target), asset.Kind == "wheel", token), token).ConfigureAwait(false);
                }
                completed += asset.Size;
            }
            progress?.Report(new("正在验证识别组件…"));
            string python = Path.Combine(staging, "tools", "python.exe");
            await VerifyAsync(python, token).ConfigureAwait(false);
            token.ThrowIfCancellationRequested();
            await File.WriteAllTextAsync(Path.Combine(staging, "ready.json"), JsonSerializer.Serialize(new { id = Bundle.Id }), token).ConfigureAwait(false);
            Directory.Move(staging, final);
            // The pointer is the commit point. Existing installations/configuration stay untouched on failure.
            string pointer = Path.Combine(root, "current.json");
            string pending = Path.Combine(final, "current.pending.json");
            await File.WriteAllTextAsync(pending, JsonSerializer.Serialize(new Installed(Bundle.Id, name)), token).ConfigureAwait(false);
            token.ThrowIfCancellationRequested();
            File.Move(pending, pointer, true); published = true;
            progress?.Report(new("组件已就绪，保存后启用", 100));
            return Path.Combine(final, "tools", "python.exe");
        } finally {
            // Remove only this operation's unpublished directory; verified downloads are retained for retry.
            var incomplete = Directory.Exists(staging) ? staging : !published && Directory.Exists(final) ? final : null;
            if (incomplete != null) {
                try { Directory.Delete(incomplete, true); }
                catch (IOException) { progress?.Report(new("未完成的组件暂未清理，可稍后重试")); }
                catch (UnauthorizedAccessException) { progress?.Report(new("未完成的组件暂未清理，请检查目录权限")); }
            }
        }
    }
    internal static string SafePath(string root, string relative)
    {
        root = Path.GetFullPath(root);
        string path = Path.GetFullPath(Path.Combine(root, relative.Replace('/', Path.DirectorySeparatorChar)));
        if (!path.Equals(root, StringComparison.OrdinalIgnoreCase) && !path.StartsWith(root + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("组件文件路径无效");
        if (relative.Contains(':') || Path.IsPathRooted(relative)) throw new InvalidDataException("组件文件路径无效");
        return path;
    }
    internal static void Extract(string archive, string destination, bool wheel, CancellationToken token)
    {
        Directory.CreateDirectory(destination);
        using var zip = ZipFile.OpenRead(archive);
        long expanded = 0;
        foreach (var entry in zip.Entries) {
            token.ThrowIfCancellationRequested();
            string name = entry.FullName.Replace('\\', '/');
            SafePath(destination, name);
            if (((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000) throw new InvalidDataException("组件压缩包包含无效链接");
            if (wheel) {
                int data = name.IndexOf(".data/", StringComparison.Ordinal);
                if (data >= 0) {
                    string tail = name[(data + 6)..];
                    if (tail.StartsWith("purelib/", StringComparison.Ordinal)) name = tail[8..];
                    else if (tail.StartsWith("platlib/", StringComparison.Ordinal)) name = tail[8..];
                    else continue; // CLI entry points/headers are not needed by the OCR worker.
                }
            }
            string path = SafePath(destination, name);
            if (name.EndsWith('/')) { Directory.CreateDirectory(path); continue; }
            expanded += entry.Length;
            if (expanded > 2L * 1024 * 1024 * 1024) throw new InvalidDataException("组件解压大小异常");
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            entry.ExtractToFile(path, true);
        }
    }
    internal static async Task<bool> ValidFileAsync(string path, string hash, string algorithm, long size, CancellationToken token)
    {
        if (!File.Exists(path) || new FileInfo(path).Length != size) return false;
        await using var input = File.OpenRead(path);
        var digest = algorithm == "SHA512" ? await SHA512.HashDataAsync(input, token).ConfigureAwait(false) : await SHA256.HashDataAsync(input, token).ConfigureAwait(false);
        return Convert.ToHexString(digest).Equals(hash, StringComparison.OrdinalIgnoreCase);
    }
    static async Task DownloadAsync(Asset asset, string path, long completed, IProgress<RuntimeProgress>? progress, CancellationToken token)
    {
        if (await ValidFileAsync(path, asset.Hash, asset.Algorithm, asset.Size, token).ConfigureAwait(false)) return;
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token); timeout.CancelAfter(TimeSpan.FromMinutes(10));
        string partial = path + ".partial";
        try {
            using var response = await Client.GetAsync(asset.Url, HttpCompletionOption.ResponseHeadersRead, timeout.Token).ConfigureAwait(false);
            response.EnsureSuccessStatusCode();
            if (response.RequestMessage?.RequestUri?.Scheme != "https") throw new InvalidDataException("组件下载地址无效");
            await using (var source = await response.Content.ReadAsStreamAsync(timeout.Token).ConfigureAwait(false))
            await using (var output = new FileStream(partial, FileMode.Create, FileAccess.Write, FileShare.None, 81920, true)) {
                var buffer = new byte[81920]; long received = 0; var watch = Stopwatch.StartNew();
                int count;
                while ((count = await source.ReadAsync(buffer, timeout.Token).ConfigureAwait(false)) != 0) {
                    received += count;
                    if (received > asset.Size) throw new InvalidDataException("组件大小与清单不符");
                    await output.WriteAsync(buffer.AsMemory(0, count), timeout.Token).ConfigureAwait(false);
                    if (watch.ElapsedMilliseconds >= 150) {
                        progress?.Report(new($"正在下载组件 · {(completed + received) / 1048576.0:F1} / {DownloadBytes / 1048576.0:F1} MB", (completed + received) * 100.0 / DownloadBytes));
                        watch.Restart();
                    }
                }
            }
            if (!await ValidFileAsync(partial, asset.Hash, asset.Algorithm, asset.Size, timeout.Token).ConfigureAwait(false)) throw new InvalidDataException("组件校验失败，请重试");
            File.Move(partial, path, true);
        } catch (OperationCanceledException) when (!token.IsCancellationRequested) { throw new TimeoutException("组件下载超时，请检查网络后重试"); }
        finally { if (File.Exists(partial)) File.Delete(partial); }
    }
    static async Task VerifyAsync(string python, CancellationToken token)
    {
        string script = Path.Combine(AppContext.BaseDirectory, "ocr_local.py");
        if (!File.Exists(script)) throw new InvalidOperationException("缺少识别组件脚本，请重新安装译取");
        var start = new ProcessStartInfo(python) { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add("-I"); start.ArgumentList.Add(script); start.ArgumentList.Add("--prepare");
        using var process = Process.Start(start) ?? throw new InvalidOperationException("无法启动识别组件");
        var output = process.StandardOutput.ReadToEndAsync(); var errors = process.StandardError.ReadToEndAsync();
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token); timeout.CancelAfter(TimeSpan.FromMinutes(2));
        try {
            await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
            var result = await output.ConfigureAwait(false); await errors.ConfigureAwait(false);
            if (process.ExitCode != 0) throw new InvalidOperationException("识别组件验证失败，请重试或使用 Windows OCR");
            using var json = JsonDocument.Parse(result);
            if (!json.RootElement.GetProperty("ready").GetBoolean()) throw new InvalidOperationException("识别组件尚未就绪");
        } catch (OperationCanceledException) when (!token.IsCancellationRequested) { throw new TimeoutException("识别组件验证超时，请重试"); }
        finally {
            if (!process.HasExited) process.Kill(true);
            await process.WaitForExitAsync().ConfigureAwait(false);
            await output.ConfigureAwait(false); await errors.ConfigureAwait(false);
        }
    }
}
