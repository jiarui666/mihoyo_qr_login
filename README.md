# miHoYo QRCode Login Tool

通过米游社 APP 扫码登录，自动获取 `stoken` / `ltoken` / `cookie_token` 等凭证，并写入 `config.yaml`

方便对接 [MihoyoBBSTools](https://github.com/Womsxd/MihoyoBBSTools) 的自动签到与米游币任务

无需短信验证、无需 Geetest 滑块，**最稳定的登录方式**

## 这个项目是干什么的？

这个脚本的主要目的：**获取 stoken 用于米游社签到任务**（以及相关自动任务）

## 功能

> 典型用途：初始化或更新 MihoyoBBSTools 的登录凭证。

- 终端内直接显示二维码，扫码即登录米游社
- 获取并输出：
  - `stoken_v2` + `mid` + `stuid`
  - `ltoken` + `cookie_token`
  - 完整 Cookie 字符串（v1 + v2 命名）
- 凭证自动写入`config.yaml`（脚本同级目录，不存在则自动创建）

## 环境要求

- Python 3.10+
- 依赖库：

```bash
pip install httpx pyyaml qrcode
```

## 使用方法

### 1. 克隆仓库

```bash
git clone https://github.com/jiarui666/mihoyo_qr_login.git
cd mihoyo-qrcode-login
```

### 2. 安装依赖

```bash
pip install httpx pyyaml qrcode
```

### 3. 运行脚本

```bash
python qr_login.py
```

### 4. 扫码登录

1. 终端会显示一个二维码
2. 打开 **米游社 APP** -> 我的 -> 右上角 **扫一扫**
3. 扫描终端中的二维码
4. 在 APP 上点击 **确认登录**
5. 脚本自动获取所有凭证并写入 `config.yaml`

## 输出示例

```
============================================================
  凭证汇总
============================================================
  stuid:        123456789
  stoken:       v2_xxxxxxxxxxxxxxxxxxxxx
  mid:          abcdefg_mhy
  ltoken:       v2_xxxxxxxxxxxxxxxxxxxxx
  cookie_token: v2_xxxxxxxxxxxxxxxxxxxxx
============================================================

[OK] 凭证已写入: /path/config.yaml
```

## 生成的 config.yaml 格式

```yaml
stuid: '123456789'
stoken: v2_xxxxxxxxxxxxxxxxxxxxx
mid: abcdefg_mhy
cookie: account_id=123456789; account_id_v2=123456789; ...
```

如果 `config.yaml` 已存在且包含 `account` 列表结构（MihoyoBBSTools 格式），脚本会更新第一个账号的凭���。

## 自定义配置路径

通过环境变量 `CONFIG_PATH` 指定输出路径：

```bash
# Linux / macOS
CONFIG_PATH=/path/to/my_config.yaml python qr_login.py

# Windows PowerShell
$env:CONFIG_PATH="C:\path\to\my_config.yaml"; python qr_login.py
```

## 注意事项

- `config.yaml` 包含敏感凭证信息，**请勿提交到公开仓库**
- Token 有效期有限，失效后重新运行脚本即可刷新

## 免责声明

本工具仅用于 **本人账号管理与自动化运维**。请勿用于任何违反米游社服务条款的用途。使用造成的账号风险由使用者自行承担。
