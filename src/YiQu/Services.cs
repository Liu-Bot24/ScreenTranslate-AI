using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace YiQu;

/// <summary>Encrypts API keys with Windows DPAPI for the current user.</summary>
public static class Secrets
{
    public static string Protect(string value) => string.IsNullOrEmpty(value) ? "" : Convert.ToBase64String(Transform(Encoding.UTF8.GetBytes(value), true));
    public static string Unprotect(string value) => string.IsNullOrEmpty(value) ? "" : Encoding.UTF8.GetString(Transform(Convert.FromBase64String(value), false));

    static byte[] Transform(byte[] bytes, bool protect)
    {
        var input = new Blob { Size = bytes.Length, Data = Marshal.AllocHGlobal(bytes.Length) };
        Blob output = default;
        try {
            Marshal.Copy(bytes, 0, input.Data, bytes.Length);
            bool ok = protect
                ? CryptProtectData(ref input, null, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, UiForbidden, out output)
                : CryptUnprotectData(ref input, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero, UiForbidden, out output);
            if (!ok) throw new CryptographicException("API Key 无法解密，请重新填写");
            var result = new byte[output.Size];
            Marshal.Copy(output.Data, result, 0, result.Length);
            return result;
        } finally {
            for (int i = 0; i < input.Size; i++) Marshal.WriteByte(input.Data, i, 0);
            Marshal.FreeHGlobal(input.Data);
            if (output.Data != IntPtr.Zero) LocalFree(output.Data);
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    const uint UiForbidden = 1;
    [StructLayout(LayoutKind.Sequential)] struct Blob { public int Size; public IntPtr Data; }
    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool CryptProtectData(ref Blob input, string? description, IntPtr entropy, IntPtr reserved, IntPtr prompt, uint flags, out Blob output);
    [DllImport("crypt32.dll", SetLastError = true)] static extern bool CryptUnprotectData(ref Blob input, IntPtr description, IntPtr entropy, IntPtr reserved, IntPtr prompt, uint flags, out Blob output);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr value);
}

/// <summary>Settings in %LOCALAPPDATA%\YiQu\settings.json, written atomically.</summary>
public static class SettingsStore
{
    public static readonly string DirectoryPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "YiQu");
    public static string FilePath => Path.Combine(DirectoryPath, "settings.json");
    internal static readonly JsonSerializerOptions Json = new() { WriteIndented = true, PropertyNameCaseInsensitive = true };
    static readonly string[] OcrProviders = { "windows", "rapidocr", "tesseract", "vision" };

    public static AppSettings Load()
    {
        if (!File.Exists(FilePath)) return new();
        var settings = JsonSerializer.Deserialize<AppSettings>(File.ReadAllText(FilePath), Json) ?? throw new InvalidDataException("配置文件无效");
        Validate(settings);
        foreach (var service in settings.Services)
            if (service.SystemPrompt == TranslationService.PreviousDefaultPrompt) service.SystemPrompt = TranslationService.DefaultPrompt;
        return settings;
    }

    public static void Save(AppSettings settings)
    {
        Validate(settings);
        AtomicWrite(FilePath, JsonSerializer.Serialize(settings, Json));
    }

    /// <summary>Rejects files with missing values instead of silently replacing them with defaults.</summary>
    internal static void Validate(AppSettings s)
    {
        if (s.Services is null || s.Ocr is null || string.IsNullOrWhiteSpace(s.PrimaryLanguage) || string.IsNullOrWhiteSpace(s.SecondaryLanguage))
            throw new InvalidDataException("配置文件无效");
        foreach (var v in s.Services)
            if (v is null || v.Name is null || v.Endpoint is null || v.Model is null || v.ProtectedApiKey is null || v.SystemPrompt is null)
                throw new InvalidDataException("配置文件无效");
        var o = s.Ocr;
        if (o.Provider is null || o.Language is null || o.LocalPythonPath is null || o.TesseractPath is null || o.TesseractLanguages is null || o.Endpoint is null || o.Model is null || o.ProtectedApiKey is null)
            throw new InvalidDataException("配置文件无效");
        if (!OcrProviders.Contains(o.Provider)) throw new InvalidDataException("配置文件中的 OCR 引擎无效");
    }

    internal static void AtomicWrite(string path, string content)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try {
            File.WriteAllText(temp, content, new UTF8Encoding(false));
            File.Move(temp, path, true);
        } finally {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }
}

/// <summary>Translation history; keeps the latest entries plus every favorite.</summary>
public static class HistoryStore
{
    const int Limit = 300;
    static string FilePath => Path.Combine(SettingsStore.DirectoryPath, "history.json");

    public static List<HistoryEntry> Load() =>
        File.Exists(FilePath) ? JsonSerializer.Deserialize<List<HistoryEntry>>(File.ReadAllText(FilePath), SettingsStore.Json) ?? new() : new();
    public static void Save(List<HistoryEntry> items) => SettingsStore.AtomicWrite(FilePath, JsonSerializer.Serialize(items, SettingsStore.Json));
    public static void Add(HistoryEntry item)
    {
        var items = Load();
        items.Insert(0, item);
        Save(items.Where((x, i) => x.Favorite || i < Limit).ToList());
    }
}

/// <summary>OpenAI-compatible chat completions, shared by translation and vision OCR.</summary>
public static class ChatApi
{
    const int MaxResponseBytes = 4 * 1024 * 1024;
    static readonly HttpClient Client = new(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(90), MaxResponseContentBufferSize = MaxResponseBytes };

    /// <summary>Accepts HTTPS, or HTTP to this computer; rejects credentials, queries and fragments in the URL.</summary>
    public static Uri ValidateEndpoint(string endpoint)
    {
        if (!Uri.TryCreate(endpoint, UriKind.Absolute, out var uri) || !string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Fragment) || !string.IsNullOrEmpty(uri.Query))
            throw new ArgumentException("接口地址无效");
        if (uri.Scheme != "https" && !(uri.Scheme == "http" && uri.IsLoopback))
            throw new ArgumentException("接口地址需使用 HTTPS（本机服务可用 HTTP）");
        return uri;
    }

    /// <summary>Posts <paramref name="body"/> and returns the first choice's text (empty when the model returned none).</summary>
    public static async Task<string> CompleteAsync(string endpoint, string protectedKey, object body, CancellationToken token)
    {
        var uri = ValidateEndpoint(endpoint);
        string key = Secrets.Unprotect(protectedKey);
        if (string.IsNullOrWhiteSpace(key) && !uri.IsLoopback) throw new InvalidOperationException("未填写 API Key");
        using var request = new HttpRequestMessage(HttpMethod.Post, uri) { Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json") };
        if (!string.IsNullOrWhiteSpace(key)) request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", key);
        try {
            using var response = await Client.SendAsync(request, token);
            if (!response.IsSuccessStatusCode) throw new InvalidOperationException($"请求失败（HTTP {(int)response.StatusCode}），请检查 API Key、模型或余额");
            if (response.Content.Headers.ContentLength > MaxResponseBytes) throw new InvalidOperationException("响应内容过大");
            await using var stream = await response.Content.ReadAsStreamAsync(token);
            using var json = await JsonDocument.ParseAsync(stream, cancellationToken: token);
            if (!json.RootElement.TryGetProperty("choices", out var choices) || choices.ValueKind != JsonValueKind.Array || choices.GetArrayLength() == 0
                || !choices[0].TryGetProperty("message", out var message) || !message.TryGetProperty("content", out var content))
                throw new InvalidOperationException("响应格式无效");
            return content.ValueKind switch {
                JsonValueKind.String => content.GetString() ?? "",
                // Some vision models return a list of content parts.
                JsonValueKind.Array => string.Join("\n", content.EnumerateArray().Where(p => p.TryGetProperty("text", out var t) && t.ValueKind == JsonValueKind.String).Select(p => p.GetProperty("text").GetString())),
                _ => ""
            };
        }
        catch (HttpRequestException) { throw new InvalidOperationException("无法连接服务，请检查网络和接口地址"); }
        catch (JsonException) { throw new InvalidOperationException("响应格式无效"); }
    }
}

public static class TranslationEngine
{
    public const int MaxServices = 12;
    const int MaxConcurrent = 4;

    /// <summary>
    /// Picks the automatic target. Chinese-primary pairs are resolved here; for other pairs the model
    /// gets an explicit conditional target rather than a guess that all Latin text is English.
    /// </summary>
    public static string ResolveTarget(string text, AppSettings settings)
    {
        int han = Regex.Matches(text, @"[\p{IsCJKUnifiedIdeographs}]").Count;
        int letters = text.Count(char.IsLetter);
        bool chinese = letters > 0 && han * 2 >= letters && !Regex.IsMatch(text, @"[\p{IsHiragana}\p{IsKatakana}\p{IsHangulSyllables}]");
        bool primaryChinese = settings.PrimaryLanguage.Contains("中文", StringComparison.Ordinal) || settings.PrimaryLanguage.StartsWith("zh", StringComparison.OrdinalIgnoreCase);
        if (primaryChinese) return chinese ? settings.SecondaryLanguage : settings.PrimaryLanguage;
        return $"{settings.PrimaryLanguage}（如果原文已是 {settings.PrimaryLanguage}，则翻译为 {settings.SecondaryLanguage}）";
    }

    /// <summary>Queries every enabled service; each result or failure is reported separately through <paramref name="onResult"/>.</summary>
    public static async Task TranslateAsync(string text, string target, IReadOnlyList<TranslationService> services, Action<TranslationResult> onResult, CancellationToken token)
    {
        if (string.IsNullOrWhiteSpace(text)) throw new ArgumentException("请输入要翻译的文本");
        var enabled = services.Where(s => s.Enabled).ToArray();
        if (enabled.Length > MaxServices) throw new InvalidOperationException($"最多同时启用 {MaxServices} 个翻译服务");
        if (enabled.Length == 0) throw new InvalidOperationException("没有已启用的翻译服务");
        using var gate = new SemaphoreSlim(MaxConcurrent);
        await Task.WhenAll(enabled.Select(async service => {
            await gate.WaitAsync(token);
            try {
                var result = await TranslateOneAsync(text, target, service, token);
                token.ThrowIfCancellationRequested();
                onResult(new(service.Name, result));
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
            catch (OperationCanceledException) { onResult(new(service.Name, "", "请求超时")); }
            catch (Exception e) when (e is ArgumentException or InvalidOperationException or CryptographicException or FormatException) { onResult(new(service.Name, "", e.Message)); }
            finally { gate.Release(); }
        }));
    }

    internal static async Task<string> TranslateOneAsync(string text, string target, TranslationService service, CancellationToken token)
    {
        if (string.IsNullOrWhiteSpace(service.Model)) throw new ArgumentException("未设置模型");
        var prompt = service.SystemPrompt.Replace("{target}", target, StringComparison.Ordinal);
        var body = new { model = service.Model, stream = false, messages = new[] { new { role = "system", content = prompt }, new { role = "user", content = text } } };
        var result = await ChatApi.CompleteAsync(service.Endpoint, service.ProtectedApiKey, body, token);
        return string.IsNullOrWhiteSpace(result) ? throw new InvalidOperationException("未返回译文") : result;
    }
}
