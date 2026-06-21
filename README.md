# 樱茗文字版

樱茗是一个先从文字开始的个人 AI 伙伴原型。当前版本重点做三件事：

- 固定樱茗的人设与说话方式。
- 读取你的长期记忆和个人画像。
- 支持导入 ChatGPT 导出的 `conversations.json`，生成画像草稿。

## 快速开始

```powershell
python .\yingming.py chat
```

没有配置模型 API 时，樱茗会进入离线占位模式，回复会比较简单，但记忆、指令和项目结构都能先跑通。

如果你有 OpenAI 兼容接口，可以设置环境变量：

```powershell
$env:YINGMING_API_KEY="你的 key"
$env:YINGMING_MODEL="gpt-4o-mini"
python .\yingming.py chat
```

可选环境变量：

```powershell
$env:YINGMING_BASE_URL="https://api.openai.com/v1"
$env:YINGMING_MODEL="你的模型名"
$env:YINGMING_TEMPERATURE="0.8"
```

如果你使用 DeepSeek，桌宠里可以直接点 `连接`，填入 API Key 后保存。配置会写入本机的：

```text
data\local_settings.json
```

这个文件已经被 `.gitignore` 排除，不会备份到 GitHub。DeepSeek 的默认配置为：

```text
Base URL: https://api.deepseek.com
Model: deepseek-v4-flash
```

也可以用环境变量启动：

```powershell
$env:DEEPSEEK_API_KEY="你的 DeepSeek key"
python .\yingming.py pet
```

## Web 交互界面

```powershell
python .\yingming.py web
```

默认地址：

```text
http://127.0.0.1:8765
```

网页里可以聊天、写入长期记忆、编辑用户画像，也可以上传 ChatGPT 导出的 `conversations.json` 生成画像草稿。

如果浏览器打不开 `127.0.0.1:8765`，通常是因为这个命令没有运行，或者运行它的终端被关闭了。`127.0.0.1` 是你自己的电脑，必须有本地服务在监听端口，浏览器才能打开。

## 桌面宠物

```powershell
python .\yingming.py pet
```

也可以双击：

```text
yingming_pet.pyw
```

或运行：

```text
start_pet.bat
```

桌宠版会显示一个置顶小窗口，可以拖动、聊天、打开记忆体、连接 DeepSeek、编辑用户画像。收起后可以点 `展开` 恢复，也可以双击头像恢复；右键樱茗窗口可以展开聊天、连接 DeepSeek、切换置顶或退出。

樱茗的人设方向是“温柔、机灵、有真实相处感的 AI 伙伴”：她可以主动接话、有自己的观察和判断，也会保持分寸，坦诚自己是 AI，不假装成人类或现实女友。

启动时，樱茗会先用本机时间、最近聊天、长期记忆和待确认记忆生成一句本地欢迎语；如果已经接入 DeepSeek，桌宠会在后台再润色成更自然的智能开场白。这个过程不会阻塞窗口打开，也不会在你已经开始操作后抢走当前气泡。

`记忆体` 会展示待确认记忆和当前长期记忆。接入 DeepSeek 后，樱茗会在每轮聊天后尝试把你明确说出的稳定偏好、目标和项目线索整理成待确认记忆；你确认后才会进入长期记忆。手动新增时也可以先点 `加入待确认`，检查无误后再点 `确认到长期`。如果确实要跳过确认，也可以点 `直接长期`。

`画像` 可以根据当前长期记忆生成画像草稿。草稿会先进入编辑框，你检查、删改后点 `保存画像`，才会写入正式的 `data\profile.md`。

如果在 `连接` 里开启 `自动总结用户画像`，长期记忆发生变化后，樱茗会在后台自动刷新正式画像。待确认记忆不会进入画像，只有确认到长期记忆之后才会参与总结。

## Windows exe

已经可以打包成便携版：

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\package_desktop.ps1
```

生成位置：

```text
dist\YingmingPet\YingmingPet.exe
```

双击 `YingmingPet.exe` 即可启动。注意不要只把这个 exe 单独挪走，它需要同目录下的 `app` 和 `runtime` 文件夹。

## 聊天内指令

在 `chat` 模式里可以输入：

- `/退出`：结束聊天。
- `/记住 内容`：把内容写入长期记忆。
- `/回忆`：查看当前长期记忆。
- `/画像`：查看当前用户画像。
- `/帮助`：查看指令。

如果你的 Windows 终端对中文输入不友好，也可以用英文别名：

- `/exit`
- `/remember 内容`
- `/memory`
- `/profile`
- `/help`

## 导入 ChatGPT 记录

从 ChatGPT 导出数据后，把 `conversations.json` 放到 `imports/chatgpt/` 里，然后运行：

```powershell
python .\yingming.py import-chatgpt .\imports\chatgpt\conversations.json
```

仓库里也有一个很小的测试文件：

```powershell
python .\yingming.py import-chatgpt .\imports\chatgpt\sample_conversations.json
```

这个命令不会自动覆盖你的正式画像，而是生成：

```text
data/profile_draft.md
data/user_corpus.jsonl
```

你可以先检查草稿，再手动把合适的内容合并进 `data/profile.md` 或通过 `/记住` 加入长期记忆。

如果用 PowerShell 查看中文文件，请加上 UTF-8 编码：

```powershell
Get-Content .\data\profile_draft.md -Encoding UTF8
```

## 文件说明

- `personas/yingming.md`：樱茗的人设、语气和边界。
- `data/profile.md`：你的个人画像，适合放稳定、经过确认的信息。
- `data/memory.json`：长期记忆和待确认记忆，适合放偏好、习惯、目标、专属梗。
- `data/chat_history.jsonl`：本地聊天历史。
- `data/local_settings.json`：本机模型连接设置，可能包含 API key，不会提交到 GitHub。
- `imports/chatgpt/`：放 ChatGPT 导出文件。
