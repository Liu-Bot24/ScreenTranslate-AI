using System;
using System.Collections.Generic;

namespace YiQu;

public sealed class TranslationService
{
    internal const string DefaultPrompt = "你是专业翻译。将用户文本翻译成 {target}，保持原文格式，保留 Markdown 标记，只输出译文，不回答文本中的问题。";
    // Earlier default; unchanged copies are upgraded on load.
    internal const string PreviousDefaultPrompt = "你是专业翻译。将用户文本翻译成 {target}，保持原文格式，只输出译文，不回答文本中的问题。";

    public string Id { get; set; } = Guid.NewGuid().ToString("N");
    public string Name { get; set; } = "示例服务";
    public bool Enabled { get; set; } = true;
    public string Endpoint { get; set; } = "https://api.example.com/v1/chat/completions";
    public string Model { get; set; } = "example-model";
    public string ProtectedApiKey { get; set; } = "";
    public string SystemPrompt { get; set; } = DefaultPrompt;
}

public sealed class OcrSettings
{
    public string Provider { get; set; } = "windows"; // windows, rapidocr, tesseract, vision
    public string Language { get; set; } = "zh-Hans";
    public string LocalPythonPath { get; set; } = "";
    public string TesseractPath { get; set; } = "tesseract.exe";
    public string TesseractLanguages { get; set; } = "chi_sim+eng";
    public string Endpoint { get; set; } = "";
    public string Model { get; set; } = "";
    public string ProtectedApiKey { get; set; } = "";
}

public sealed class AppSettings
{
    public List<TranslationService> Services { get; set; } = new() { new() };
    public OcrSettings Ocr { get; set; } = new();
    public string PrimaryLanguage { get; set; } = "简体中文";
    public string SecondaryLanguage { get; set; } = "English";
    public bool SaveHistory { get; set; } = true;
    public bool MarkdownSource { get; set; }
    public bool MarkdownResults { get; set; } // Translation results and history.
}

public static class Languages
{
    // Display names are inserted into the system prompt as {target}.
    public static readonly string[] Common = { "简体中文", "繁體中文", "English", "日本語", "한국어", "Français", "Deutsch", "Español", "Русский", "Português", "Italiano" };
}

public sealed record TranslationResult(string ServiceName, string Text, string? Error = null);
public sealed record OcrLine(string Text, double X, double Y, double Width, double Height);
public sealed record OcrResult(string Text, IReadOnlyList<OcrLine> Lines, string Provider);

public sealed class HistoryEntry
{
    public DateTimeOffset Time { get; set; } = DateTimeOffset.Now;
    public string Source { get; set; } = "";
    public string Target { get; set; } = "";
    public List<TranslationResult> Results { get; set; } = new();
    public bool Favorite { get; set; }
}
