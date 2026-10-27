# 开发说明

## 环境

- Windows 10/11 x64，.NET 8 SDK
- 打包安装程序需要 Inno Setup 6（`winget install JRSoftware.InnoSetup`）

## 构建

```powershell
./scripts/build.ps1            # 生成 dist\YiQu.exe 和 dist\YiQu.Cli.exe（依赖 .NET 8 运行时）
./scripts/build_installer.ps1  # 生成 release\YiQu-Setup-<版本>.exe（自带运行时）
```

版本号取自 `src/YiQu/YiQu.csproj` 中的 `<Version>`。

## 检查

`YiQu.Cli.exe` 用于开发检查，不会读取剪贴板，也不会修改已保存的设置和历史：

| 参数 | 内容 |
| --- | --- |
| `--self-test` | 配置校验、目标语言、接口地址规则、密钥加密，以及一次本机回环 HTTP 翻译请求 |
| `--interaction-test` | 实际执行界面点击：剪贴板文字与图片翻译、清除、朗读启停、Markdown 开关 |
| `--runtime-test [目录]` | RapidOCR 组件的校验、取消、下载、验证与复用（首次会下载约 128 MB） |
| `--render-ui <目录>` | 使用示例数据离屏渲染各窗口的浅色、深色截图 |

## 代码结构

| 位置 | 内容 |
| --- | --- |
| `src/YiQu/MainWindow.cs` | 主窗口：输入、结果卡片、快捷键与托盘 |
| `src/YiQu/SettingsWindow.cs`、`HistoryWindow.cs` | 设置、历史与收藏 |
| `src/YiQu/ShellWindow.cs`、`Theme.cs`、`Theme.xaml` | 自绘标题栏、明暗配色、控件样式 |
| `src/YiQu/Services.cs` | 设置与历史存储、API Key 加密、翻译请求 |
| `src/YiQu/OcrEngine.cs`、`ocr_local.py` | 各 OCR 引擎；RapidOCR 以常驻 Python 进程运行 |
| `src/YiQu/RapidOcrRuntime.cs`、`Assets/rapidocr-runtime.json` | RapidOCR 组件的下载清单（固定地址、大小与哈希）和安装 |
| `src/YiQu/NativeDesktop.cs`、`CaptureOverlay.cs` | 全局快捷键、读取选中文字、框选截图 |
| `src/YiQu/MarkdownView.cs`、`Speech.cs` | Markdown 渲染、朗读 |
| `src/YiQu.Cli/` | 开发检查 |
| `installer/` | Inno Setup 脚本与简体中文界面文本 |
| `scripts/make_icon.py` | 生成 `Assets/YiQu.ico` |
