using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Interop;

namespace YiQu;

public enum Hotkey { Selection = 1, Capture, Input, CaptureOcr, Clipboard }

/// <summary>Registers the global Alt+letter shortcuts on a window.</summary>
public sealed class HotkeyManager : IDisposable
{
    static readonly Dictionary<Hotkey, char> Letters = new() {
        [Hotkey.Selection] = 'Q', [Hotkey.Capture] = 'W', [Hotkey.Input] = 'E', [Hotkey.CaptureOcr] = 'R', [Hotkey.Clipboard] = 'C'
    };
    const uint ModAlt = 0x1, ModNoRepeat = 0x4000;
    const int WmHotkey = 0x312;
    private readonly IntPtr handle;
    private readonly HwndSource source;
    private readonly Action<Hotkey> callback;
    private readonly List<Hotkey> registered = new();
    private bool disposed;
    public IReadOnlyList<Hotkey> Failed { get; }
    public static string Label(Hotkey key) => "Alt+" + Letters[key];

    public HotkeyManager(Window owner, Action<Hotkey> callback)
    {
        this.callback = callback;
        handle = new WindowInteropHelper(owner).EnsureHandle();
        source = HwndSource.FromHwnd(handle) ?? throw new InvalidOperationException("快捷键初始化失败");
        source.AddHook(Hook);
        var failed = new List<Hotkey>();
        foreach (var (key, letter) in Letters)
        {
            if (RegisterHotKey(handle, (int)key, ModAlt | ModNoRepeat, letter)) registered.Add(key);
            else failed.Add(key);
        }
        Failed = failed.AsReadOnly();
    }
    private IntPtr Hook(IntPtr hwnd, int message, IntPtr wparam, IntPtr lparam, ref bool handled)
    {
        if (message == WmHotkey && !disposed) { handled = true; callback((Hotkey)wparam.ToInt32()); }
        return IntPtr.Zero;
    }
    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        foreach (var key in registered) UnregisterHotKey(handle, (int)key);
        source.RemoveHook(Hook);
    }
    [DllImport("user32.dll", SetLastError = true)] private static extern bool RegisterHotKey(IntPtr hwnd, int id, uint modifiers, uint key);
    [DllImport("user32.dll")] private static extern bool UnregisterHotKey(IntPtr hwnd, int id);
}

public static class NativeDesktop
{
    private static readonly SemaphoreSlim SelectionGate = new(1, 1);

    // Must be called on the WPF dispatcher before activating the translation window.
    public static async Task<string> ReadSelectionAsync()
    {
        await SelectionGate.WaitAsync();
        try
        {
            var foreground = GetForegroundWindow();
            if (foreground == IntPtr.Zero) return "";
            GetWindowThreadProcessId(foreground, out var foregroundPid);
            if (foregroundPid == (uint)Environment.ProcessId) return "";
            try
            {
                var focused = AutomationElement.FocusedElement;
                if (focused is not null && !focused.Current.IsPassword && focused.Current.ProcessId == foregroundPid &&
                    focused.TryGetCurrentPattern(TextPattern.Pattern, out var pattern))
                {
                    var text = string.Join(Environment.NewLine, ((TextPattern)pattern).GetSelection().Select(r => r.GetText(-1)));
                    if (!string.IsNullOrWhiteSpace(text)) return text;
                }
                // Do not send Copy into a password field, even if its app supports copying.
                if (focused?.Current.IsPassword == true) return "";
            }
            catch (Exception ex) when (ex is ElementNotAvailableException or InvalidOperationException or COMException)
            { /* Some applications do not expose UI Automation TextPattern; Copy is the fallback. */ }

            // Wait for the initiating Alt hotkey to be released before synthesizing Ctrl+C.
            for (int i = 0; i < 50 && ModifiersDown(); i++) await Task.Delay(20);
            if (ModifiersDown() || GetForegroundWindow() != foreground) return "";
            var previous = SnapshotClipboard();
            Clipboard.Clear();
            uint ourSequence = GetClipboardSequenceNumber();
            bool selectionCopied = false;
            try
            {
                if (GetForegroundWindow() != foreground) return "";
                var input = new[] { Key(0x11), Key(0x43), Key(0x43, true), Key(0x11, true) };
                if (SendInput((uint)input.Length, input, Marshal.SizeOf<INPUT>()) != input.Length)
                    throw new InvalidOperationException("无法读取选中文字，请复制后按 Alt+C 翻译");
                for (int i = 0; i < 40; i++)
                {
                    await Task.Delay(20);
                    var sequence = GetClipboardSequenceNumber();
                    if (sequence == ourSequence) continue;
                    var clipboardOwner = GetClipboardOwner();
                    GetWindowThreadProcessId(clipboardOwner, out var ownerPid);
                    // Never mistake a clipboard manager or unrelated app's new content for the selection.
                    if (!IsSelectionClipboardOwner(foregroundPid, ownerPid)) return "";
                    ourSequence = sequence;
                    selectionCopied = true;
                    try
                    {
                        var selected = Clipboard.ContainsText() ? Clipboard.GetText() : "";
                        // Reject content if another application took clipboard ownership while reading.
                        return RefreshSelectionSequence(foregroundPid, ref ourSequence) ? selected : "";
                    }
                    catch (COMException)
                    {
                        RefreshSelectionSequence(foregroundPid, ref ourSequence);
                        return "";
                    }
                }
                return "";
            }
            finally
            {
                // If another application changed the clipboard, leave that newer content untouched.
                for (int attempt = 0; attempt < 4; attempt++)
                {
                    // Check on EVERY attempt: another app may complete Copy during retry delay.
                    GetWindowThreadProcessId(GetClipboardOwner(), out var currentOwnerPid);
                    if (!CanRestoreClipboard(ourSequence, GetClipboardSequenceNumber(),
                            foregroundPid, currentOwnerPid, selectionCopied)) break;
                    try
                    {
                        if (previous is null) Clipboard.Clear(); else Clipboard.SetDataObject(previous, true);
                        break;
                    }
                    catch (COMException) when (attempt < 3) { await Task.Delay(30); }
                }
            }
        }
        finally { SelectionGate.Release(); }
    }

    private static bool RefreshSelectionSequence(uint foregroundPid, ref uint sequence)
    {
        // GetText may trigger OLE delayed rendering, which increments the sequence again.
        // Adopt that sequence only while the source still owns the clipboard.
        GetWindowThreadProcessId(GetClipboardOwner(), out var ownerPid);
        if (!IsSelectionClipboardOwner(foregroundPid, ownerPid)) return false;
        sequence = GetClipboardSequenceNumber();
        return true;
    }

    // Pure policies without clipboard access, so the self-test can check them.
    internal static bool IsSelectionClipboardOwner(uint foregroundPid, uint clipboardOwnerPid) =>
        foregroundPid != 0 && foregroundPid == clipboardOwnerPid;

    internal static bool CanRestoreClipboard(uint observedSequence, uint currentSequence,
        uint foregroundPid, uint clipboardOwnerPid, bool selectionCopied) =>
        observedSequence == currentSequence &&
        (!selectionCopied || IsSelectionClipboardOwner(foregroundPid, clipboardOwnerPid));

    private static DataObject? SnapshotClipboard()
    {
        var original = Clipboard.GetDataObject();
        if (original is null) return null;
        var snapshot = new DataObject();
        foreach (var format in original.GetFormats(false))
        {
            var data = original.GetData(format, false);
            if (data is null) throw new InvalidOperationException("无法读取选中文字，请复制后按 Alt+C 翻译");
            // Materialize streams before the original clipboard owner loses ownership.
            if (data is System.IO.Stream stream)
            {
                var copy = new System.IO.MemoryStream();
                var oldPosition = stream.CanSeek ? stream.Position : 0;
                if (stream.CanSeek) stream.Position = 0;
                stream.CopyTo(copy); copy.Position = 0;
                if (stream.CanSeek) stream.Position = oldPosition;
                data = copy;
            }
            snapshot.SetData(format, data, false);
        }
        return snapshot;
    }

    private static bool ModifiersDown() => (GetAsyncKeyState(0x12) & 0x8000) != 0 ||
        (GetAsyncKeyState(0x11) & 0x8000) != 0 || (GetAsyncKeyState(0x10) & 0x8000) != 0 ||
        (GetAsyncKeyState(0x5B) & 0x8000) != 0 || (GetAsyncKeyState(0x5C) & 0x8000) != 0;
    private static INPUT Key(ushort key, bool up = false) => new() { type = 1, data = new INPUTUNION { keyboard = new KEYBDINPUT { virtualKey = key, flags = up ? 2u : 0 } } };
    [StructLayout(LayoutKind.Sequential)] private struct INPUT { public uint type; public INPUTUNION data; }
    // The mouse member is never used; it gives the union the size SendInput expects.
    [StructLayout(LayoutKind.Explicit)] private struct INPUTUNION
    {
        [FieldOffset(0)] public KEYBDINPUT keyboard;
        [FieldOffset(0)] public MOUSEINPUT mouse;
    }
    [StructLayout(LayoutKind.Sequential)] private struct KEYBDINPUT { public ushort virtualKey, scanCode; public uint flags, time; public UIntPtr extraInfo; }
    [StructLayout(LayoutKind.Sequential)] private struct MOUSEINPUT { public int x, y; public uint mouseData, flags, time; public UIntPtr extraInfo; }
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern IntPtr GetClipboardOwner();
    [DllImport("user32.dll")] private static extern uint GetClipboardSequenceNumber();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
    [DllImport("user32.dll")] private static extern short GetAsyncKeyState(int key);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, INPUT[] inputs, int size);
}
