@echo off



setlocal enabledelayedexpansion



REM ========================================



REM ScreenTranslate-AI 一键打包脚本



REM 双击运行，自动打包成单exe文件



REM ========================================







title ScreenTranslate-AI 打包工具







echo.



echo ========================================



echo     ScreenTranslate-AI 打包工具



echo ========================================



echo.



echo 正在准备打包环境，请稍候...



echo.







REM 自动切换到脚本所在目录的上级目录（项目根目录）



cd /d "%~dp0\.."







REM 检查是否在正确的项目目录



if not exist "main.py" (



    echo [错误] 未找到 main.py 文件



    echo 请确保脚本位于项目的 scripts 目录中



    echo 当前目录: %CD%



    echo.



    pause



    exit /b 1



)







REM 检查虚拟环境是否存在



if not exist ".venv" (



    echo [错误] 虚拟环境不存在



    echo 正在创建虚拟环境...



    python -m venv .venv



    if !errorlevel! neq 0 (



        echo [错误] 无法创建虚拟环境，请检查Python安装



        pause



        exit /b 1



    )



)







REM 激活虚拟环境



echo [步骤1] 激活虚拟环境...



call .venv\Scripts\activate.bat







REM 安装/更新必要依赖



echo [步骤2] 检查并安装依赖...



pip install --upgrade pip --quiet



pip install pyinstaller --quiet



pip install -r requirements.txt --quiet







if !errorlevel! neq 0 (



    echo [错误] 依赖安装失败



    pause



    exit /b 1



)







REM 清理之前的构建



echo [步骤3] 清理构建缓存...



if exist "build" rmdir /s /q "build" 2>nul



if exist "dist" rmdir /s /q "dist" 2>nul



if exist "*.spec" del /q "*.spec" 2>nul







REM 检查图标文件



echo [步骤4] 准备资源文件...



set ICON_PATH=ico.png



if not exist "%ICON_PATH%" (



    echo [警告] 未找到应用图标 ico.png，将使用默认图标



    set ICON_PATH=



) else (



    echo [信息] 使用应用图标: %ICON_PATH%



)







REM 执行打包



echo [步骤5] 开始打包应用程序...



echo 这可能需要几分钟时间，请耐心等待...



echo.







REM 构建单文件可执行程序 (调试模式)



if defined ICON_PATH (



    pyinstaller --onefile --clean --noconfirm ^



        --name "ScreenTranslate-AI" ^



        --icon "%ICON_PATH%" ^



        --add-data "src;src" ^



        --add-data "ico.png;." ^



        --hidden-import "easyocr" ^



        --hidden-import "torch" ^



        --hidden-import "cv2" ^



        --hidden-import "numpy" ^



        --hidden-import "PIL" ^



        --hidden-import "PyQt6" ^



        --hidden-import "PyQt6.QtCore" ^



        --hidden-import "PyQt6.QtGui" ^



        --hidden-import "PyQt6.QtWidgets" ^



        --hidden-import "httpx" ^



        --hidden-import "pynput" ^



        --collect-all "easyocr" ^



        --collect-all "torchvision" ^
        --collect-all "cv2" ^




        --exclude-module "torchaudio" ^



        --exclude-module "matplotlib" ^





        --exclude-module "pandas" ^



        --exclude-module "notebook" ^



        --exclude-module "IPython" ^



        --noupx ^



        main.py



) else (



    pyinstaller --onefile --clean --noconfirm ^



        --name "ScreenTranslate-AI" ^



        --add-data "src;src" ^



        --add-data "ico.png;." ^



        --hidden-import "easyocr" ^



        --hidden-import "torch" ^



        --hidden-import "cv2" ^



        --hidden-import "numpy" ^



        --hidden-import "PIL" ^



        --hidden-import "PyQt6" ^



        --hidden-import "PyQt6.QtCore" ^



        --hidden-import "PyQt6.QtGui" ^



        --hidden-import "PyQt6.QtWidgets" ^



        --hidden-import "httpx" ^



        --hidden-import "pynput" ^



        --collect-all "easyocr" ^



        --collect-all "torchvision" ^
        --collect-all "cv2" ^




        --exclude-module "torchaudio" ^



        --exclude-module "matplotlib" ^





        --exclude-module "pandas" ^



        --exclude-module "notebook" ^



        --exclude-module "IPython" ^



        --noupx ^



        main.py



)







if !errorlevel! neq 0 (



    echo.



    echo [错误] 打包失败！



    echo 请检查错误信息并重试



    echo.



    pause



    exit /b 1



)







REM 检查输出文件



if exist "dist\ScreenTranslate-AI.exe" (



    echo.



    echo ========================================



    echo           打包成功完成！



    echo ========================================



    echo.







    REM 获取文件大小



    for %%F in ("dist\ScreenTranslate-AI.exe") do (



        set size=%%~zF



        set /a sizeMB=!size!/1024/1024



    )







    echo 输出文件: dist\ScreenTranslate-AI.exe



    echo 文件大小: !sizeMB! MB



    echo.



    echo 使用说明：



    echo ✓ 双击 dist\ScreenTranslate-AI.exe 即可运行



    echo ✓ 无需安装任何依赖，可直接在其他电脑使用



    echo ✓ 首次运行可能被杀毒软件误报，请添加信任



    echo ✓ 默认快捷键：Alt+3



    echo.







    REM 创建便捷启动脚本



    echo [信息] 创建便捷启动脚本...



    echo @echo off > dist\启动应用.bat



    echo cd /d "%%~dp0" >> dist\启动应用.bat



    echo start "" "ScreenTranslate-AI.exe" >> dist\启动应用.bat







    echo 额外创建: dist\启动应用.bat （静默启动）



    echo.







) else (



    echo.



    echo [错误] 打包完成但未找到输出文件



    echo 请检查 dist 目录



    echo.



    pause



    exit /b 1



)







REM 清理临时文件



echo [清理] 删除临时文件...



if exist "build" rmdir /s /q "build" 2>nul



if exist "*.spec" del /q "*.spec" 2>nul







echo ========================================



echo        🎉 打包任务全部完成！🎉



echo ========================================



echo.



echo 输出目录: %CD%\dist\



echo 可执行文件: ScreenTranslate-AI.exe



echo.







REM 询问是否打开输出目录



choice /C YN /M "是否打开输出目录查看文件？(Y/N)"



if !errorlevel! equ 1 (



    explorer "dist"



)







echo.



echo 按任意键退出...



pause >nul



