"""
全局快捷键管理模块

在Windows上使用 WM_HOTKEY 隐藏消息窗口注册全局热键，
其他平台 fallback 到 pynput 监听，实现跨平台兼容性。
默认支持Alt+3触发截图，可配置其他组合键。
处理权限问题和键盘事件冲突，确保不阻塞主线程。
"""

import sys
import platform
import threading
import logging
import ctypes
from ctypes import wintypes
from typing import Optional, Callable, Set, Dict, Any, Iterable
from dataclasses import dataclass
from enum import Enum

try:
    from pynput import keyboard
    from pynput.keyboard import Key, KeyCode, Listener
except ImportError:
    raise ImportError("请安装pynput库: pip install pynput")

from PyQt6.QtCore import QObject, pyqtSignal, QThread


class ModifierKey(Enum):
    """修饰键枚举"""
    CTRL = "ctrl"
    SHIFT = "shift"
    ALT = "alt"
    CMD = "cmd"  # macOS专用
    WIN = "win"  # Windows专用


@dataclass
class HotkeyConfig:
    """快捷键配置"""
    name: str                          # 快捷键名称
    modifiers: Set[ModifierKey]        # 修饰键集合
    key: str                          # 主键
    callback: Optional[Callable] = None  # 回调函数
    description: str = ""              # 描述


class HotkeyManager(QObject):
    """全局快捷键管理器"""

    # 快捷键触发信号
    hotkey_triggered = pyqtSignal(str)  # 快捷键名称
    # 错误信号
    error_occurred = pyqtSignal(str)
    # 状态变化信号
    status_changed = pyqtSignal(bool)  # True: 监听中, False: 已停止

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

        # 快捷键配置字典
        self._hotkey_configs: Dict[str, HotkeyConfig] = {}

        # 监听器
        self._listener: Optional[Listener] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._win_hotkey_worker: Optional['_WinHotkeyWorker'] = None

        # 当前按下的键集合
        self._pressed_keys: Set[Any] = set()

        # 监听状态
        self._is_listening = False
        self._should_stop = False

        # 系统平台
        self._platform = platform.system().lower()

        # 初始化默认快捷键
        self._setup_default_hotkeys()

    def _setup_default_hotkeys(self):
        """设置默认快捷键"""
        # 默认截图快捷键: Alt+3
        default_screenshot_config = HotkeyConfig(
            name="screenshot",
            modifiers={ModifierKey.CTRL, ModifierKey.SHIFT},
            key="x",
            description="触发截图功能"
        )

        self.register_hotkey(default_screenshot_config)

    def register_hotkey(self, config: HotkeyConfig) -> bool:
        """
        注册快捷键

        Args:
            config: 快捷键配置

        Returns:
            bool: 是否注册成功
        """
        try:
            # 验证配置
            if not self._validate_hotkey_config(config):
                return False

            # 存储配置
            self._hotkey_configs[config.name] = config

            self.logger.info(f"注册快捷键: {config.name} - {self._format_hotkey_display(config)}")
            return True

        except Exception as e:
            self.logger.error(f"注册快捷键失败: {str(e)}")
            self.error_occurred.emit(f"注册快捷键失败: {str(e)}")
            return False

    def unregister_hotkey(self, name: str) -> bool:
        """
        注销快捷键

        Args:
            name: 快捷键名称

        Returns:
            bool: 是否注销成功
        """
        try:
            if name in self._hotkey_configs:
                del self._hotkey_configs[name]
                self.logger.info(f"注销快捷键: {name}")
                return True
            return False

        except Exception as e:
            self.logger.error(f"注销快捷键失败: {str(e)}")
            return False

    def set_hotkey_callback(self, name: str, callback: Callable) -> bool:
        """
        设置快捷键回调函数

        Args:
            name: 快捷键名称
            callback: 回调函数

        Returns:
            bool: 是否设置成功
        """
        try:
            if name in self._hotkey_configs:
                self._hotkey_configs[name].callback = callback
                return True
            return False

        except Exception as e:
            self.logger.error(f"设置快捷键回调失败: {str(e)}")
            return False

    def update_hotkey_config(self, name: str,
                              modifiers: Iterable[str],
                              key: str) -> bool:
        """根据配置更新快捷键"""
        try:
            if not key or not key.strip():
                self.logger.error("更新快捷键失败: 主键不能为空")
                return False

            modifier_set: Set[ModifierKey] = set()
            for modifier in modifiers or []:
                try:
                    modifier_enum = ModifierKey(modifier.lower())
                    modifier_set.add(modifier_enum)
                except ValueError:
                    self.logger.warning(f"忽略无效的修饰键: {modifier}")

            key = key.lower()

            if name in self._hotkey_configs:
                config = self._hotkey_configs[name]
                config.modifiers = modifier_set
                config.key = key
                self.logger.info(
                    f"更新快捷键: {name} - {self._format_hotkey_display(config)}"
                )
            else:
                config = HotkeyConfig(
                    name=name,
                    modifiers=modifier_set,
                    key=key
                )
                self.register_hotkey(config)

            return True

        except Exception as e:
            self.logger.error(f"更新快捷键配置失败: {str(e)}")
            self.error_occurred.emit(f"更新快捷键配置失败: {str(e)}")
            return False

    def start_listening(self) -> bool:
        """
        开始监听全局快捷键

        Returns:
            bool: 是否启动成功
        """
        try:
            if self._is_listening:
                self.logger.warning("快捷键监听已在运行中")
                return True

            # 检查权限
            if not self._check_permissions():
                return False

            if self._platform == "windows":
                return self._start_windows_hotkeys()
            else:
                return self._start_pynput_hotkeys()

        except Exception as e:
            self.logger.error(f"启动快捷键监听失败: {str(e)}")
            self.error_occurred.emit(f"启动快捷键监听失败: {str(e)}")
            return False

    def stop_listening(self) -> bool:
        """
        停止监听全局快捷键

        Returns:
            bool: 是否停止成功
        """
        try:
            if not self._is_listening:
                return True

            if self._platform == "windows":
                self._stop_windows_hotkeys()
            else:
                self._stop_pynput_hotkeys()

            self._is_listening = False
            self.status_changed.emit(False)
            self.logger.info("全局快捷键监听已停止")

            return True

        except Exception as e:
            self.logger.error(f"停止快捷键监听失败: {str(e)}")
            return False

    def is_listening(self) -> bool:
        """
        检查是否正在监听

        Returns:
            bool: 是否正在监听
        """
        return self._is_listening

    def get_registered_hotkeys(self) -> Dict[str, str]:
        """
        获取已注册的快捷键列表

        Returns:
            Dict[str, str]: 快捷键名称到显示文本的映射
        """
        result = {}
        for name, config in self._hotkey_configs.items():
            result[name] = self._format_hotkey_display(config)
        return result

    def _start_pynput_hotkeys(self) -> bool:
        """启动基于pynput的跨平台监听"""
        try:
            self._should_stop = False
            self._pressed_keys.clear()

            self._listener = Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release
            )

            self._listener_thread = threading.Thread(
                target=self._listener_worker,
                daemon=True
            )
            self._listener.start()
            self._listener_thread.start()

            self._is_listening = True
            self.status_changed.emit(True)
            self.logger.info("全局快捷键监听已启动 (pynput)")
            return True

        except Exception as e:
            self.logger.error(f"启动pynput监听失败: {e}")
            self.error_occurred.emit(f"启动快捷键监听失败: {e}")
            return False

    def _stop_pynput_hotkeys(self) -> None:
        """停止pynput监听"""
        self._should_stop = True

        if self._listener:
            self._listener.stop()

        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2.0)

        self._listener = None
        self._listener_thread = None
        self._pressed_keys.clear()

    def _start_windows_hotkeys(self) -> bool:
        """启动基于WM_HOTKEY的Windows监听"""
        try:
            if self._win_hotkey_worker and self._win_hotkey_worker.isRunning():
                self._win_hotkey_worker.stop()
                self._win_hotkey_worker.wait(500)

            self._win_hotkey_worker = _WinHotkeyWorker(self._hotkey_configs)
            self._win_hotkey_worker.hotkey_triggered.connect(self._on_worker_hotkey)
            self._win_hotkey_worker.error_occurred.connect(self.error_occurred.emit)
            self._win_hotkey_worker.finished.connect(self._on_windows_worker_finished)
            self._win_hotkey_worker.start()

            self._is_listening = True
            self.status_changed.emit(True)
            self.logger.info("全局快捷键监听已启动 (WM_HOTKEY)")
            return True

        except Exception as e:
            self.logger.error(f"启动Windows热键监听失败: {e}")
            self.error_occurred.emit(f"启动快捷键监听失败: {e}")
            return False

    def _stop_windows_hotkeys(self) -> None:
        """停止Windows热键监听"""
        if self._win_hotkey_worker:
            try:
                self._win_hotkey_worker.stop()
                self._win_hotkey_worker.wait(500)
            except Exception as e:
                self.logger.warning(f"停止Windows热键监听时出错: {e}")
            try:
                self._win_hotkey_worker.finished.disconnect(self._on_windows_worker_finished)
            except Exception:
                pass
        self._win_hotkey_worker = None

    def _on_worker_hotkey(self, name: str) -> None:
        """处理来自Windows热键线程的事件"""
        try:
            config = self._hotkey_configs.get(name)
            if config:
                self.logger.info(f"快捷键触发: {name}")
                self.hotkey_triggered.emit(name)
                if config.callback:
                    try:
                        config.callback()
                    except Exception as callback_error:
                        self.logger.error(f"快捷键回调执行失败: {callback_error}")
            else:
                self.logger.warning(f"收到未知快捷键: {name}")
        except Exception as e:
            self.logger.error(f"处理热键回调失败: {e}")

    def _on_windows_worker_finished(self) -> None:
        """Windows热键线程结束回调"""
        self.logger.info("Windows热键监听线程已结束")
        if self._is_listening and self._platform == "windows":
            self._is_listening = False
            self.status_changed.emit(False)

    def _listener_worker(self):
        """监听器工作线程"""
        try:
            if self._listener:
                self._listener.join()
        except Exception as e:
            if not self._should_stop:
                self.logger.error(f"快捷键监听器异常: {str(e)}")
                self.error_occurred.emit(f"快捷键监听器异常: {str(e)}")

    def _on_key_press(self, key):
        """按键按下事件处理"""
        try:
            # 添加到已按下的键集合
            self._pressed_keys.add(key)

            # 检查是否匹配任何快捷键
            self._check_hotkey_match()

        except Exception as e:
            self.logger.error(f"按键处理异常: {str(e)}")

    def _on_key_release(self, key):
        """按键释放事件处理"""
        try:
            # 从已按下的键集合中移除
            self._pressed_keys.discard(key)

        except Exception as e:
            self.logger.error(f"按键释放处理异常: {str(e)}")

    def _check_hotkey_match(self):
        """检查当前按键组合是否匹配任何快捷键"""
        try:
            for name, config in self._hotkey_configs.items():
                if self._is_hotkey_pressed(config):
                    self.logger.info(f"快捷键触发: {name}")

                    # 发射信号
                    self.hotkey_triggered.emit(name)

                    # 调用回调函数
                    if config.callback:
                        try:
                            config.callback()
                        except Exception as e:
                            self.logger.error(f"快捷键回调执行失败: {str(e)}")

                    # 清除按键状态，避免重复触发
                    self._pressed_keys.clear()
                    break

        except Exception as e:
            self.logger.error(f"快捷键匹配检查异常: {str(e)}")

    def _is_hotkey_pressed(self, config: HotkeyConfig) -> bool:
        """
        检查指定的快捷键是否被按下

        Args:
            config: 快捷键配置

        Returns:
            bool: 是否被按下
        """
        try:
            # 检查修饰键
            def _modifier_pressed(mod: ModifierKey) -> bool:
                mapping = {
                    ModifierKey.CTRL: (Key.ctrl_l, Key.ctrl_r),
                    ModifierKey.SHIFT: (Key.shift_l, Key.shift_r),
                    ModifierKey.ALT: (Key.alt_l, Key.alt_r),
                    ModifierKey.CMD: (Key.cmd_l, Key.cmd_r),
                    ModifierKey.WIN: (Key.cmd,)
                }

                keys = mapping.get(mod, ())

                # Windows上CMD映射为WIN键，macOS上WIN无意义
                if mod == ModifierKey.CMD and self._platform != "darwin":
                    return False
                if mod == ModifierKey.WIN and self._platform != "windows":
                    return False

                return any(key in self._pressed_keys for key in keys)

            for modifier in config.modifiers:
                if not _modifier_pressed(modifier):
                    return False

            # 检查主键
            main_key_pressed = False
            target_key = config.key.lower()

            for pressed_key in self._pressed_keys:
                if hasattr(pressed_key, 'char') and pressed_key.char:
                    if pressed_key.char.lower() == target_key:
                        main_key_pressed = True
                        break
                elif hasattr(pressed_key, 'name'):
                    if pressed_key.name.lower() == target_key:
                        main_key_pressed = True
                        break

            return main_key_pressed

        except Exception as e:
            self.logger.error(f"快捷键匹配检查异常: {str(e)}")
            return False

    def _validate_hotkey_config(self, config: HotkeyConfig) -> bool:
        """
        验证快捷键配置

        Args:
            config: 快捷键配置

        Returns:
            bool: 是否有效
        """
        try:
            if not config.name or not config.key:
                self.logger.error("快捷键名称和按键不能为空")
                return False

            # 检查是否与现有快捷键冲突
            for existing_name, existing_config in self._hotkey_configs.items():
                if existing_name != config.name:
                    if (existing_config.modifiers == config.modifiers and
                        existing_config.key.lower() == config.key.lower()):
                        self.logger.error(f"快捷键冲突: {config.name} 与 {existing_name}")
                        return False

            return True

        except Exception as e:
            self.logger.error(f"快捷键配置验证异常: {str(e)}")
            return False

    def _format_hotkey_display(self, config: HotkeyConfig) -> str:
        """
        格式化快捷键显示文本

        Args:
            config: 快捷键配置

        Returns:
            str: 显示文本
        """
        try:
            parts = []

            # 添加修饰键
            if ModifierKey.CTRL in config.modifiers:
                parts.append("Ctrl")
            if ModifierKey.SHIFT in config.modifiers:
                parts.append("Shift")
            if ModifierKey.ALT in config.modifiers:
                parts.append("Alt")
            if ModifierKey.CMD in config.modifiers:
                parts.append("Cmd")
            if ModifierKey.WIN in config.modifiers:
                parts.append("Win")

            # 添加主键
            parts.append(config.key.upper())

            return "+".join(parts)

        except Exception as e:
            self.logger.error(f"快捷键显示格式化异常: {str(e)}")
            return f"{config.name} (格式化失败)"

    def _check_permissions(self) -> bool:
        """
        检查系统权限

        Returns:
            bool: 是否有足够权限
        """
        try:
            # macOS权限检查
            if self._platform == "darwin":
                try:
                    # 尝试创建一个测试监听器
                    test_listener = Listener(
                        on_press=lambda key: None,
                        on_release=lambda key: None
                    )
                    test_listener.start()
                    test_listener.stop()
                    return True
                except Exception:
                    self.error_occurred.emit(
                        "macOS需要辅助功能权限。请前往 系统偏好设置 > 安全性与隐私 > 隐私 > 辅助功能，"
                        "添加此应用程序。"
                    )
                    return False

            # Windows和Linux通常不需要特殊权限
            return True

        except Exception as e:
            self.logger.error(f"权限检查异常: {str(e)}")
            self.error_occurred.emit(f"权限检查失败: {str(e)}")
            return False

    def cleanup(self):
        """清理资源"""
        try:
            self.stop_listening()
            self.logger.info("快捷键管理器已清理")
        except Exception as e:
            self.logger.error(f"清理资源异常: {str(e)}")


class _WinHotkeyWorker(QThread):
    """使用隐藏消息窗口注册全局热键的工作线程 (Windows专用)"""

    hotkey_triggered = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    MOD_ALT = 0x0001
    MOD_CONTROL = 0x0002
    MOD_SHIFT = 0x0004
    MOD_WIN = 0x0008
    WM_HOTKEY = 0x0312
    WM_CLOSE = 0x0010
    WM_DESTROY = 0x0002

    def __init__(self, configs: Dict[str, HotkeyConfig]):
        super().__init__()
        self._configs = {
            name: HotkeyConfig(
                name=config.name,
                modifiers=set(config.modifiers),
                key=config.key,
                description=config.description
            )
            for name, config in configs.items()
        }
        self._hwnd: Optional[int] = None
        self._id_to_name: Dict[int, str] = {}

    def run(self):
        try:
            self._message_loop()
        except Exception as e:
            self.error_occurred.emit(f"全局热键监听异常: {e}")

    def stop(self):
        if self._hwnd:
            ctypes.windll.user32.PostMessageW(self._hwnd, self.WM_CLOSE, 0, 0)

    def _message_loop(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long,
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT

        worker = self

        @WNDPROC
        def _wnd_proc(hWnd, msg, wParam, lParam):
            if msg == worker.WM_HOTKEY:
                hotkey_id = int(wParam)
                name = worker._id_to_name.get(hotkey_id)
                if name:
                    worker.hotkey_triggered.emit(name)
                return 0
            elif msg == worker.WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hWnd, msg, wParam, lParam)

        class WNDCLASS(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint),
                ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", ctypes.c_void_p),
                ("hCursor", ctypes.c_void_p),
                ("hbrBackground", ctypes.c_void_p),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        hInstance = kernel32.GetModuleHandleW(None)
        class_name = "ScreenTranslateHotkeyWnd"

        wndclass = WNDCLASS()
        wndclass.style = 0
        wndclass.lpfnWndProc = ctypes.cast(_wnd_proc, ctypes.c_void_p).value
        wndclass.cbClsExtra = 0
        wndclass.cbWndExtra = 0
        wndclass.hInstance = hInstance
        wndclass.hIcon = 0
        wndclass.hCursor = 0
        wndclass.hbrBackground = 0
        wndclass.lpszMenuName = None
        wndclass.lpszClassName = class_name

        atom = user32.RegisterClassW(ctypes.byref(wndclass))
        if not atom:
            # 可能已注册
            pass

        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
            wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, ctypes.c_void_p, wintypes.HINSTANCE, ctypes.c_void_p
        ]
        user32.CreateWindowExW.restype = wintypes.HWND

        self._hwnd = user32.CreateWindowExW(
            0, class_name, "", 0,
            0, 0, 0, 0,
            0, 0, hInstance, None
        )

        if not self._hwnd:
            error_code = kernel32.GetLastError()
            logging.getLogger(__name__).error(f"创建消息窗口失败，错误代码: {error_code}")
            self.error_occurred.emit("全局热键监听启动失败: 无法创建消息窗口")
            return

        if not self._register_hotkeys(user32):
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
            return

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._unregister_hotkeys(user32)
        if self._hwnd:
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None

    def _register_hotkeys(self, user32) -> bool:
        self._id_to_name.clear()

        next_id = 100
        for name, config in self._configs.items():
            modifiers = self._convert_modifiers(config.modifiers)
            vk = self._convert_key(config.key)

            if vk is None:
                logging.getLogger(__name__).error(f"无法注册热键 '{name}': 不支持的按键 '{config.key}'")
                self.error_occurred.emit(f"无法注册热键 '{name}': 不支持的按键 '{config.key}'")
                continue

            vk_codes = [vk]

            # 为数字键额外注册数字小键盘，对注重数字输入的用户友好
            if isinstance(vk, tuple):
                vk_codes = list(vk)

            success_count = 0
            for code in vk_codes:
                if not user32.RegisterHotKey(self._hwnd, next_id, modifiers, code):
                    error_code = ctypes.windll.kernel32.GetLastError()
                    logging.getLogger(__name__).error(f"注册热键失败: {name} 键码 {code} (错误代码: {error_code})")
                    self.error_occurred.emit(f"注册热键失败: {name} 键码 {code} (错误代码: {error_code})")
                    continue
                self._id_to_name[next_id] = name
                logging.getLogger(__name__).info(f"成功注册Windows热键: {name} 键码 {code} (ID: {next_id})")
                success_count += 1
                next_id += 1

        if not self._id_to_name:
            logging.getLogger(__name__).error("未能注册任何全局热键")
            self.error_occurred.emit("未能注册任何全局热键")
            return False

        logging.getLogger(__name__).info(f"Windows热键注册完成，共注册 {len(self._id_to_name)} 个热键")
        return True

    def _unregister_hotkeys(self, user32) -> None:
        for hotkey_id in list(self._id_to_name.keys()):
            try:
                user32.UnregisterHotKey(self._hwnd, hotkey_id)
            except Exception:
                pass
        self._id_to_name.clear()

    def _convert_modifiers(self, modifiers: Set[ModifierKey]) -> int:
        flags = 0
        for modifier in modifiers:
            if modifier == ModifierKey.ALT:
                flags |= self.MOD_ALT
            elif modifier == ModifierKey.CTRL:
                flags |= self.MOD_CONTROL
            elif modifier == ModifierKey.SHIFT:
                flags |= self.MOD_SHIFT
            elif modifier == ModifierKey.WIN:
                flags |= self.MOD_WIN
        return flags

    def _convert_key(self, key: str) -> Optional[int]:
        if not key:
            return None

        key = key.strip().upper()

        if len(key) == 1:
            base_vk = ord(key)

            if key.isdigit():
                numpad_map = {
                    '0': 0x60,
                    '1': 0x61,
                    '2': 0x62,
                    '3': 0x63,
                    '4': 0x64,
                    '5': 0x65,
                    '6': 0x66,
                    '7': 0x67,
                    '8': 0x68,
                    '9': 0x69,
                }
                return (base_vk, numpad_map[key])

            return base_vk

        function_keys = {f"F{i}": 0x6F + i for i in range(1, 25)}
        special_keys = {
            "SPACE": 0x20,
            "ENTER": 0x0D,
            "ESC": 0x1B,
            "TAB": 0x09,
            "BACKSPACE": 0x08,
            "UP": 0x26,
            "DOWN": 0x28,
            "LEFT": 0x25,
            "RIGHT": 0x27,
            "DELETE": 0x2E,
            "HOME": 0x24,
            "END": 0x23,
            "PAGEUP": 0x21,
            "PAGEDOWN": 0x22,
        }

        if key in function_keys:
            return function_keys[key]
        if key in special_keys:
            return special_keys[key]

        vk = ctypes.windll.user32.VkKeyScanW(ord(key[0]))
        if vk == -1:
            return None
        return vk & 0xFF


# 全局快捷键管理器实例
_global_hotkey_manager: Optional[HotkeyManager] = None


def get_hotkey_manager() -> HotkeyManager:
    """
    获取全局快捷键管理器实例（单例模式）

    Returns:
        HotkeyManager: 快捷键管理器实例
    """
    global _global_hotkey_manager
    if _global_hotkey_manager is None:
        _global_hotkey_manager = HotkeyManager()
    return _global_hotkey_manager


def cleanup_hotkey_manager():
    """清理全局快捷键管理器"""
    global _global_hotkey_manager
    if _global_hotkey_manager:
        _global_hotkey_manager.cleanup()
        _global_hotkey_manager = None
