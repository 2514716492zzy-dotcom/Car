# ELEC3848_ProposedFunction-main 声音输出（speaker/TTS）整理

> 说明：这个仓库的“声音输出”主要是 **TTS 语音播放**，不是 Arduino `tone()` 蜂鸣器方式。

## 1) 主要入口与调用链

### A. 主入口初始化（`main.py`）

- `from modules.text_to_speech import TextToSpeech`
  - 作用：导入 TTS 引擎类。
- `tts_engine = TextToSpeech()`
  - 作用：在程序启动时初始化一个全局语音引擎实例，后续所有播报都复用它。

### B. 对外播报封装（`main.py`）

- `speak_blocking(text)`
  - 作用：同步播报（会等待播报完成），适合关键提示（如校准步骤提示）。
- `speak_async(text)`
  - 作用：异步播报（后台线程），适合不想阻塞主流程时使用。
- `wait_for_speaking_to_finish()`
  - 作用：等待当前播报结束（通过 `speaking_event` 状态管理）。

### C. 业务触发点（`main.py`）

- 校准流程中多次调用 `speak_blocking(...)`
  - 作用：语音提示用户当前校准阶段、失败提示、完成提示。
- 对话/响应流程中调用 `speak_async(...)`
  - 作用：机器人回复时进行语音输出，同时不中断主循环。

---

## 2) 真正“发声”的核心实现

### 文件：`modules/text_to_speech/tts_module.py`

这是 speaker 输出的核心模块，流程如下：

1. `gTTS` 把文本转成 mp3（临时文件）。
2. 使用系统命令播放 mp3（`mpg123`）。
3. 播放结束后删除临时文件。

### 关键类与方法

- `class TextToSpeech`
  - 作用：封装语音参数（voice/language/speed）与播报逻辑。

- `TextToSpeech.speak(text)`
  - 作用：统一入口，根据配置选择发声风格：
    - `normal` -> `_speak_normal`
    - `cute_sox` -> `_speak_cute_sox`

- `_speak_normal(text)`
  - 作用：标准音色播报。
  - 关键点：
    - `gTTS(...).save(temp_response.mp3)` 生成语音文件
    - `os.system("mpg123 ...")` 播放

- `_speak_cute_sox(text)`
  - 作用：可爱音色播报（先生成普通音频，再用 `sox` 变调）。
  - 关键点：
    - `sox temp_normal.mp3 temp_cute.mp3 pitch 300`
    - 然后 `mpg123 temp_cute.mp3` 播放

- `speak_normal(text)` / `speak_cute_sox(text)`
  - 作用：历史兼容封装（直接构建不同 voice 的 `TextToSpeech` 再播报）。

---

## 3) 配置项（影响 speaker 输出行为）

### 文件：`config.ini`

- `[tts]`
  - `voice = cute_sox`
    - 作用：默认音色。可选 `normal`、`cute_sox`。
  - `language = en`
    - 作用：TTS 语言代码（传给 `gTTS`）。
  - `speed = normal`
    - 作用：语速配置（映射到 `gTTS` 的 `slow` 参数）。

---

## 4) 与 face-follow 的关系

### 文件：`modules/face_detection/face_follow.py`

- `announce_action(tts, message, blocking=False)`
  - 作用：给人脸跟随流程提供通用播报接口（可阻塞/非阻塞）。
- `start_face_follow(..., tts=...)`
  - 作用：接收外部传入的 TTS 对象，理论上可在跟随状态变化时播报。
- 注意：
  - 部分示例播报调用目前是注释状态（如 `Searching` / `Moving closer` 等），说明“接口在、触发点预留了”，但默认可能没有启用全部语音提示。

---

## 5) 一句话总结（便于快速回忆）

- 这个项目的 speaker 输出主链路是：  
  `main.py`（触发） -> `TextToSpeech.speak()`（选择音色） -> `gTTS`（生成 mp3） -> `mpg123`（播放到扬声器）。

