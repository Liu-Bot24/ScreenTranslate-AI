// Developer checks for YiQu. They never read the clipboard or change saved settings and history.
//   --self-test                  pure logic and a loopback HTTP round trip
//   --interaction-test           real WPF click handlers, clipboard OCR, speech and Markdown toggles
//   --runtime-test [directory]   RapidOCR download, verification and reuse (downloads ~128 MB)
//   --render-ui <directory>      off-screen screenshots of every window with sample data
internal static class Cli
{
    [STAThread]
    static int Main(string[] args)
    {
        Console.OutputEncoding = new System.Text.UTF8Encoding(false);
        try {
            string? argument = args.Skip(1).FirstOrDefault();
            switch (args.FirstOrDefault()) {
                case "--self-test": return SelfChecks.Run();
                case "--interaction-test": return InteractionChecks.Run();
                case "--runtime-test": return RuntimeChecks.Run(argument);
                case "--render-ui" when argument != null: UiRenders.Render(argument); return 0;
                default: Console.Error.WriteLine("Usage: YiQu.Cli --self-test | --interaction-test | --runtime-test [directory] | --render-ui <directory>"); return 2;
            }
        } catch (Exception e) {
            Console.Error.WriteLine(e.GetType().Name + ": " + e.Message);
            return 1;
        }
    }
}
