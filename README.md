# SNNU Wi-Fi Console

陕西师范大学（SNNU）校园网专用的 Windows 本地控制台。它用于连接 `SNNU` Wi-Fi、完成学校 Portal 认证、管理后台守护服务，并在桌面窗口中查看实时状态和日志。

推荐 GitHub 仓库名：`snnu-wifi-console`

架构：Python 保活核心 + 原生桌面控制台 + PowerShell 安装脚本。

## 适用范围

本项目只面向陕西师范大学校园网环境：

- Wi-Fi SSID 默认为 `SNNU`
- Portal 地址默认为 `202.117.144.205:8602` 和 `202.117.144.205:8603`
- 登录线路支持：校园网、联通、移动
- 系统环境面向 Windows 11

其他学校或其他 Portal 系统大概率不能直接使用，需要自行修改 `config\snnu-config.json` 里的 Portal 地址、字段名和线路参数。

## Screenshots

![控制台首页](docs/assets/screenshot-dashboard.png)

## Features

- 自动连接 `SNNU` Wi-Fi。
- 自动检测网络连通性，并在离线时触发 Portal 登录。
- 可在系统配置里选择校园网、联通或移动线路。
- 支持 Windows Service 后台守护运行。
- 提供固定尺寸的原生桌面控制台管理服务安装、运行、配置和日志。

## Quick Start

1. 安装 Python 依赖：

```powershell
pip install -r .\requirements.txt
```

2. 创建本地配置文件：

```powershell
Copy-Item .\config\snnu-config.example.json .\config\snnu-config.json
```

3. 确保已经手动连接过一次 `SNNU` Wi-Fi，让 Windows 保存无线配置。

4. 写入账号密码：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\network\set-credentials.ps1
```

5. 单次测试：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\network\wifi-keepalive.ps1 -Once
```

6. 正式运行桌面控制台：

```powershell
.\artifacts\dist\SNNU WiFi Console\SNNU WiFi Console.exe
```

正式交付入口是 EXE。它会要求管理员权限；如果当前不是管理员，会自动弹出 UAC 提权。

源码调试入口在 `scripts\app\dev-run.bat`。它会自动创建项目内 `.venv`，安装依赖，并把 `config\snnu-config.json` 里的 `pythonPath` 固定到 `.venv\Scripts\python.exe`，避免依赖用户的 Conda 或系统 Python。

历史 Web 版已归档到 `backup\web-legacy`，不再进入正式桌面版或 EXE 打包产物。

## Desktop App

桌面控制台入口是 `desktop\app.py`，支持：

- 查看当前在线状态、SSID、IP、无线网卡和最近错误。
- 修改 SSID、Profile、网卡名、线路、用户名和密码。
- 立即执行一次 Portal 认证。
- 安装、启动、停止 Windows Service。
- 修复 Wi-Fi Profile 为所有用户可用。
- 查看和打开日志目录。
- 使用 PySide6 原生桌面 UI，关闭窗口时最小化到系统托盘。

开发环境自举：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\env\bootstrap-venv.ps1
```

如果本机默认 Python 是 3.13，推荐先创建轻量 py312 Conda 种子环境，再生成项目 `.venv`：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\env\setup-py312-conda.ps1 -Bootstrap
```

手动启动桌面控制台：

```powershell
.\scripts\app\dev-run.bat
```

打包 EXE：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build\build-exe.ps1 -Clean
```

打包产物位于：

```text
artifacts\dist\SNNU WiFi Console\SNNU WiFi Console.exe
```

## 线路选择

在桌面控制台的“连接配置”中选择网络类型：

- `校园网`
- `联通`
- `移动`

该选项会写入 `config\snnu-config.json` 的 `portalOptions.networkType`，后台服务会读取同一份配置。

## Windows Service

管理员权限运行一次：

```text
scripts\service\install-helper.bat
```

安装 helper 后，可以直接在桌面控制台里安装、启动、停止守护服务。

如果服务环境下 Portal 登录失败，在 `config\snnu-config.json` 里把 `pythonPath` 设置为完整的 `python.exe` 路径。

如需把 Wi-Fi profile 转为所有用户可用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\network\fix-wifi-profile.ps1 -Profile SNNU
```

## Project Structure

```text
config/
  snnu-config.example.json   # 可公开提交的配置模板
docs/
  运行指南.txt               # 使用说明
desktop/
  app.py                     # 原生桌面控制台入口
  assets/                    # 桌面版资源
  core/                      # Python Wi-Fi 保活与 Portal 认证核心
  controllers/               # 控制器层
  models/                    # 配置和状态模型
  services/                  # 服务编排
  views/                     # PySide6 界面
scripts/
  app/                       # 桌面启动、自启注册
  build/                     # PyInstaller 打包
  env/                       # .venv / Python 环境自举
  network/                   # Wi-Fi、Portal、热点与账号配置
  service/                   # Windows 守护服务
  admin/                     # 管理员 helper 服务
packaging/
  requirements-build.txt     # 打包依赖
  SNNU WiFi Console.spec     # PyInstaller 配置
artifacts/
  build/                     # PyInstaller 中间产物
  dist/                      # EXE 输出
backup/
  web-legacy/                # 历史 Web 版归档，不进入正式 EXE
```

## Security Notes

- `config\snnu-config.json` 会保存本地账号密码，已通过 `.gitignore` 排除。
- `config\admin-token.txt` 和 `logs/` 也已排除，公开仓库时不要手动上传。
- 首次公开到 GitHub 前，建议运行 `git status --ignored` 确认敏感文件没有进入暂存区。

## License

未指定许可证前，默认保留所有权利。公开发布前建议补充 `LICENSE`。
