# ASR Benchmark Project

本项目旨在对不同的 ASR（语音转文字）模型进行对比测试和准确率评估。支持多种主流 ASR 服务（如阿里云 FunASR、Qwen-ASR 和讯飞大模型），并集成了基于 `deepeval` (G-Eval) 的自动化评估流程。

---

## Benchmark（评估逻辑介绍）

### 结果文件与评估报告结构
本项目通过两个阶段生成最终的评估报告。识别过程产生的中间结果文件（`_result.xlsx`）和最终的评估报告（`_eval.xlsx`）在结构上具有继承关系：

#### 1. 自动化识别结果 (`_result.xlsx`)
包含 ASR 识别出的原始信息：
*   **model**: 所使用的 ASR 脚本路径。
*   **wav_file**: 测试音频文件路径。
*   **content**: ASR 识别出的完整文本。
*   **eval_time**: 识别执行的时间戳。

**识别结果示例:**

| model | wav_file | content | eval_time |
| :--- | :--- | :--- | :--- |
| scripts/asr_llm_funasr.py | data/audio_01.wav | [00:00.500 --> 00:03.200] [Speaker 0] 你好，我来面试保安岗位。 | 2026-07-28 14:00:00 |

#### 2. 最终评估报告 (`_eval.xlsx`)
该文件是 `_result.xlsx` 的增强版，**包含了原文件中的所有字段**（如 model, wav_file, content, eval_time），并在识别结果的基础上，增加以下由 G-Eval 自动计算的评分列：
*   **ground_truth**: 标准参考文本（JSON 格式）。
*   **content_accuracy**: 准确率得分 (0-1 之间)，反映识别文本与标准文本的语义一致性。
*   **reason**: 模型给出评分的具体理由，用于分析识别错误的根因。

**评估报告示例:**

| content | ground_truth | content_accuracy | reason |
| :--- | :--- | :--- | :--- |
| 你好，我来面试保安岗位。 | [{"role":"USER", "ground_truth":"你好，我来面试保安岗位。"}] | 1.0 | 识别结果与标准答案语义完全一致，无信息缺失或错误。 |
| 我在监控室查看监控。 | [{"role":"USER", "ground_truth":"在监控室负责查看监控。"}] | 0.92 | 意思表达准确，虽然措辞略有出入，但核心信息完整。 |

---

## Prerequisites (环境要求)

### 1. Python 环境
建议使用 Conda 管理两个主要的运行环境：
*   **识别环境 (interview)**: 用于运行各个 ASR 识别脚本。
    *   Python 3.8+
    *   依赖: `dashscope`, `websocket-client`, `requests`, `pandas`, `openpyxl`
*   **评估环境 (aiops)**: 用于运行识别结果的准确率评估。
    *   Python 3.9+
    *   依赖: `deepeval`, `pandas`, `openpyxl`

### 2. 环境变量配置
在使用前，必须配置以下环境变量：
```bash
# 阿里云 DashScope / OpenAI 代理密钥 (用于 FunASR, Qwen-ASR)
export OPENAI_API_KEY="your-dashscope-api-key"

# 讯飞 (iFlytek) 账号信息
export IFLYTEK_APP_ID="your-app-id"
export IFLYTEK_API_KEY="your-api-key"
export IFLYTEK_API_SECRET="your-api-secret"
```

### 3. G-Eval 评估配置
在评估环境下，需要配置 `.deepeval` 目录，确保其指向支持的 LLM 接口（如 Qwen 或 GPT-4），用于对识别结果进行语义一致性评分。

---

## How to Use (使用说明)

### 1. 单独运行 ASR 脚本
你可以直接运行特定的脚本来识别单个音频文件：

*   **阿里云 Fun-ASR (非实时，带角色分离与时间轴)**
    ```bash
    python scripts/asr_llm_funasr.py --wav_file data/面试录音1.wav
    ```
*   **阿里云 Qwen-ASR (实时)**
    ```bash
    python scripts/rtasr_llm_qwenasr.py --wav_file data/面试录音1.wav
    ```
*   **讯飞实时转文大模型 (无声纹版)**
    ```bash
    python scripts/rtasr_llm_no_voiceprint.py --wav_file data/面试录音1.wav
    ```

### 2. 自动化批量测评流程 (Benchmark)

#### 第一步：运行批量识别
使用自动化脚本遍历测试集中的音频并记录识别结果：
```bash
# 环境: interview
python scripts/eval_asr_detect.py --dataset data/评估-面试录音1.xlsx
```
*   **输入**: `data/评估-面试录音1.xlsx` (需包含 `model` 和 `wav_file` 列)
*   **输出**: `data/评估-面试录音1_result.xlsx`

#### 第二步：评估识别准确率
对识别出的文本与标准文本 (Ground Truth) 进行对比评分：
```bash
# 环境: aiops
python scripts/eval_asr_accuracy.py --dataset data/评估-面试录音1_result.xlsx --filter USER
```
*   **参数 `--filter`**: 可选，用于筛选 `ground_truth` 中的特定角色（如 `USER`）。
*   **输出**: `data/评估-面试录音1_result_eval.xlsx`

---

## 项目结构
*   `scripts/`: 包含所有 ASR 接口实现和测评脚本。
*   `data/`: 存放测试音频文件、Excel 测试集以及最终的评估结果。
*   `references/`: 存放各厂商 ASR 官方文档与 Demo 供参考。

---

## License
本项目采用 [MIT License](LICENSE) 协议。
