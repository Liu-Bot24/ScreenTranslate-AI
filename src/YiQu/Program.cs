using System;
using System.Threading;
using System.Windows;

namespace YiQu;

public static class Program
{
    [STAThread]
    public static int Main()
    {
        using var mutex = new Mutex(true, "Local\\YiQu.Desktop", out bool created);
        if (!created) { MessageBox.Show("译取已在运行，可按 Alt+E 打开。", "译取"); return 0; }
        var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
        try {
            // App-level resources also cover popups such as tooltips and combo box drop-downs.
            Theme.Initialize(); Theme.Attach(app.Resources);
            app.Run(new MainWindow(SettingsStore.Load()));
            return 0;
        } catch (Exception ex) {
            MessageBox.Show("启动失败：" + ex.Message, "译取", MessageBoxButton.OK, MessageBoxImage.Error);
            return 1;
        }
    }
}
