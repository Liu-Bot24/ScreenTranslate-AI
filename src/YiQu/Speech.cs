using System;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using Windows.Media.SpeechSynthesis;

namespace YiQu;

/// <summary>
/// Read-aloud. Text is synthesized off the UI thread into an in-memory WAV and played with winmm PlaySound.
/// SAPI's own audio output can stall on some devices, and its synchronous purge then blocks the caller;
/// stopping PlaySound returns immediately.
/// </summary>
public static class Speech
{
    [DllImport("winmm.dll", SetLastError = true)] static extern bool PlaySound(IntPtr sound, IntPtr module, uint flags);
    const uint Async = 0x1, NoDefault = 0x2, Memory = 0x4;
    static IntPtr buffer;
    static DateTime endsAt;
    /// <summary>For tests: plays real audio buffers with zeroed samples.</summary>
    internal static bool Silent { get; set; }

    public static bool Finished => buffer == IntPtr.Zero || DateTime.UtcNow >= endsAt;

    /// <summary>Synthesizes and starts playback; returns once playback has started. Call on the UI thread.</summary>
    public static async Task SpeakAsync(string text, CancellationToken token)
    {
        Stop();
        if (string.IsNullOrWhiteSpace(text)) return;
        byte[] wav = await SynthesizeAsync(text, token);
        token.ThrowIfCancellationRequested();
        var (offset, length, byteRate) = ParseWav(wav);
        if (Silent) Array.Clear(wav, offset, length);
        Stop();
        // PlaySound reads the buffer asynchronously, so it lives in unmanaged memory until Stop.
        buffer = Marshal.AllocHGlobal(wav.Length);
        Marshal.Copy(wav, 0, buffer, wav.Length);
        if (!PlaySound(buffer, IntPtr.Zero, Async | NoDefault | Memory)) { Stop(); throw new InvalidOperationException("无法播放声音"); }
        endsAt = DateTime.UtcNow + TimeSpan.FromSeconds((double)length / byteRate) + TimeSpan.FromMilliseconds(150);
    }

    public static void Stop()
    {
        if (buffer == IntPtr.Zero) return;
        PlaySound(IntPtr.Zero, IntPtr.Zero, 0);
        Marshal.FreeHGlobal(buffer);
        buffer = IntPtr.Zero;
    }

    static async Task<byte[]> SynthesizeAsync(string text, CancellationToken token)
    {
        SpeechSynthesizer synthesizer;
        try { synthesizer = new SpeechSynthesizer(); }
        catch (Exception ex) when (ex is COMException or UnauthorizedAccessException) { throw new InvalidOperationException("系统未安装可用的语音"); }
        using (synthesizer) {
            if (PickVoice(text) is { } voice) synthesizer.Voice = voice;
            using var stream = await synthesizer.SynthesizeTextToStreamAsync(text).AsTask(token);
            var bytes = new byte[checked((int)stream.Size)];
            await using var reader = stream.AsStreamForRead();
            await reader.ReadExactlyAsync(bytes, token);
            return bytes;
        }
    }

    /// <summary>Picks an installed voice for the text's script; null keeps the system default.</summary>
    static VoiceInformation? PickVoice(string text)
    {
        string language = Regex.IsMatch(text, @"[\p{IsHiragana}\p{IsKatakana}]") ? "ja"
            : Regex.IsMatch(text, @"\p{IsHangulSyllables}") ? "ko"
            : Regex.IsMatch(text, @"\p{IsCJKUnifiedIdeographs}") ? "zh"
            : Regex.IsMatch(text, @"\p{IsCyrillic}") ? "ru" : "en";
        bool Matches(VoiceInformation v) => v.Language.StartsWith(language, StringComparison.OrdinalIgnoreCase);
        var fallback = SpeechSynthesizer.DefaultVoice;
        return fallback != null && Matches(fallback) ? fallback : SpeechSynthesizer.AllVoices.FirstOrDefault(Matches);
    }

    /// <summary>Locates the sample data and byte rate in a RIFF/WAVE buffer.</summary>
    internal static (int Offset, int Length, int ByteRate) ParseWav(byte[] wav)
    {
        if (wav.Length < 12 || Encoding.ASCII.GetString(wav, 0, 4) != "RIFF" || Encoding.ASCII.GetString(wav, 8, 4) != "WAVE") throw new InvalidDataException("语音数据无效");
        int byteRate = 0;
        for (long i = 12; i + 8 <= wav.Length;) {
            string id = Encoding.ASCII.GetString(wav, (int)i, 4);
            long size = BitConverter.ToUInt32(wav, (int)i + 4);
            if (id == "fmt " && i + 20 <= wav.Length) byteRate = BitConverter.ToInt32(wav, (int)i + 16);
            else if (id == "data") {
                if (byteRate <= 0) break;
                int offset = (int)i + 8;
                return (offset, (int)Math.Min(size, wav.Length - offset), byteRate);
            }
            i += 8 + size + (size & 1);
        }
        throw new InvalidDataException("语音数据无效");
    }
}
