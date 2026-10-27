using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using YiQu;

// Fast checks of pure logic: clipboard policies, configuration validation, target language,
// endpoint rules, DPAPI and one real HTTP round trip against a loopback server.
internal static class SelfChecks
{
    static void Check(bool value, string label) { if (!value) throw new Exception("TEST FAILED: " + label); Console.WriteLine("PASS " + label); }

    public static int Run() { Verify().GetAwaiter().GetResult(); return 0; }

    static async Task Verify()
    {
        Check(NativeDesktop.IsSelectionClipboardOwner(10, 10) && !NativeDesktop.IsSelectionClipboardOwner(10, 20) && !NativeDesktop.IsSelectionClipboardOwner(0, 0), "clipboard source owner checked");
        Check(NativeDesktop.CanRestoreClipboard(8, 8, 10, 10, true) && !NativeDesktop.CanRestoreClipboard(8, 9, 10, 10, true) && !NativeDesktop.CanRestoreClipboard(8, 8, 10, 20, true)
            && NativeDesktop.CanRestoreClipboard(8, 8, 10, 0, false) && !NativeDesktop.CanRestoreClipboard(8, 9, 10, 0, false), "clipboard restore preserves newer copies");

        foreach (var bad in new[] { "{\"Services\":null}", "{\"Ocr\":null}", "{\"Services\":[{\"SystemPrompt\":null}]}" }) {
            bool rejected = false;
            try { SettingsStore.Validate(JsonSerializer.Deserialize<AppSettings>(bad)!); } catch (InvalidDataException) { rejected = true; }
            Check(rejected, "invalid configuration rejected without overwrite");
        }

        var custom = new AppSettings { PrimaryLanguage = "English", SecondaryLanguage = "日本語" };
        Check(TranslationEngine.ResolveTarget("こんにちは", custom).Contains("如果原文"), "non-Chinese automatic target uses model language condition");
        var defaults = new AppSettings();
        Check(TranslationEngine.ResolveTarget("Hello world", defaults) == "简体中文", "English to Chinese");
        Check(TranslationEngine.ResolveTarget("你好世界", defaults) == "English", "Chinese to English");

        Check(ChatApi.ValidateEndpoint("http://127.0.0.1:1234/v1/chat/completions").IsLoopback, "local model endpoint allowed");
        foreach (var url in new[] { "http://example.com/v1/chat/completions", "https://x:y@example.com/", "https://example.com/?key=foo" }) {
            bool rejected = false;
            try { ChatApi.ValidateEndpoint(url); } catch (ArgumentException) { rejected = true; }
            Check(rejected, "unsafe endpoint rejected");
        }

        const string markdown = "alpha **beta** gamma\n- item";
        Check(MarkdownView.SourceOffset(markdown, "alpha be") == markdown.IndexOf("ta"), "preview position maps inside bold text");
        Check(MarkdownView.SourceOffset(markdown, "alpha beta ") == markdown.IndexOf("gamma"), "preview position after a space skips closing markup");
        Check(MarkdownView.SourceOffset(markdown, "alpha beta gamma\r\n") == markdown.IndexOf("- item"), "preview position at a line start maps to that line");
        Check(MarkdownView.SourceOffset(markdown, "☐ alpha") == 0, "unrendered characters do not move the source position");

        var secret = "test-only-not-a-real-key";
        var encrypted = Secrets.Protect(secret);
        Check(encrypted != secret && Secrets.Unprotect(encrypted) == secret, "DPAPI roundtrip");

        var listener = new TcpListener(IPAddress.Loopback, 0); listener.Start();
        string endpoint = $"http://127.0.0.1:{((IPEndPoint)listener.LocalEndpoint).Port}/v1/chat/completions";
        // Answers one request with the given chat completion content after letting the caller inspect the request.
        Task Serve(string content, Action<JsonElement> inspect) => Task.Run(async () => {
            using var client = await listener.AcceptTcpClientAsync();
            await using var stream = client.GetStream();
            var header = new List<byte>(); var one = new byte[1];
            while (header.Count < 65536) {
                if (await stream.ReadAsync(one) == 0) throw new Exception("early EOF");
                header.Add(one[0]);
                if (header.Count >= 4 && Encoding.ASCII.GetString(header.TakeLast(4).ToArray()) == "\r\n\r\n") break;
            }
            var length = int.Parse(Encoding.ASCII.GetString(header.ToArray()).Split("\r\n").First(x => x.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)).Split(':')[1]);
            var body = new byte[length]; await stream.ReadExactlyAsync(body);
            using (var request = JsonDocument.Parse(body)) inspect(request.RootElement);
            var response = Encoding.UTF8.GetBytes("{\"choices\":[{\"message\":{\"content\":" + content + "}}]}");
            await stream.WriteAsync(Encoding.ASCII.GetBytes($"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {response.Length}\r\nConnection: close\r\n\r\n"));
            await stream.WriteAsync(response);
        });
        try {
            var server = Serve("\"你好\"", request => {
                var messages = request.GetProperty("messages");
                Check(messages[1].GetProperty("content").GetString() == "Hello", "request preserves source text");
                Check(messages[0].GetProperty("content").GetString()!.Contains("翻译成 简体中文"), "prompt receives the target language");
            });
            var result = await TranslationEngine.TranslateOneAsync("Hello", "简体中文", new TranslationService { Endpoint = endpoint, Model = "test" }, CancellationToken.None);
            Check(result == "你好", "real HTTP request and JSON response");
            await server;

            server = Serve("[{\"type\":\"text\",\"text\":\" Line 1\"},{\"type\":\"text\",\"text\":\"Line 2 \"}]", request =>
                Check(request.GetProperty("messages")[0].GetProperty("content")[1].GetProperty("image_url").GetProperty("url").GetString()!.StartsWith("data:image/png;base64,"), "vision request carries the image"));
            var ocr = await OcrEngine.RecognizeAsync(new byte[] { 1 }, new OcrSettings { Provider = "vision", Endpoint = endpoint, Model = "test" }, CancellationToken.None);
            Check(ocr.Text == "Line 1\nLine 2", "vision OCR joins content parts");
            await server;
        } finally { listener.Stop(); }

        using var canceled = new CancellationTokenSource(); canceled.Cancel();
        bool cancellation = false;
        try { await TranslationEngine.TranslateAsync("hello", "中文", new[] { new TranslationService() }, _ => { }, canceled.Token); }
        catch (OperationCanceledException) { cancellation = true; }
        Check(cancellation, "cancellation propagates");

        var failed = new List<TranslationResult>();
        await TranslationEngine.TranslateAsync("hello", "中文", new[] { new TranslationService { Endpoint = "https://example.invalid/v1/chat/completions" } }, failed.Add, CancellationToken.None);
        Check(failed.Count == 1 && failed[0].Error == "未填写 API Key", "missing key produces explicit failure without network");
    }
}
