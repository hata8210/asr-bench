# ASR Benchmark Project

This project aims to compare and evaluate various ASR (Automatic Speech Recognition) models. It supports multiple mainstream ASR services (such as Alibaba Cloud FunASR, Qwen-ASR, and iFlytek) and integrates an automated evaluation workflow based on `deepeval` (G-Eval).

[中文说明请参考 README_CN.md](./README_CN.md)

---

## Benchmark (Evaluation Logic)

### Result File and Evaluation Report Structure
This project generates a final evaluation report through two stages. The intermediate result file (`_result.xlsx`) generated during the recognition process and the final evaluation report (`_eval.xlsx`) have a hierarchical relationship in terms of structure:

#### 1. Automated Recognition Results (`_result.xlsx`)
Contains the raw information recognized by the ASR:
*   **model**: The path of the ASR script used.
*   **wav_file**: The path of the test audio file.
*   **content**: The full text recognized by the ASR.
*   **eval_time**: The timestamp of the recognition execution.

**Recognition Result Example:**

| model | wav_file | content | eval_time |
| :--- | :--- | :--- | :--- |
| scripts/asr_llm_funasr.py | data/audio_01.wav | [00:00.500 --> 00:03.200] [Speaker 0] Hello, I'm here for the security guard interview. | 2026-07-28 14:00:00 |

#### 2. Final Evaluation Report (`_eval.xlsx`)
This file is an enhanced version of `_result.xlsx`, **containing all fields from the original file** (such as model, wav_file, content, eval_time), and adds the following scoring columns calculated automatically by G-Eval:
*   **ground_truth**: Standard reference text (JSON format).
*   **content_accuracy**: Accuracy score (between 0-1), reflecting the semantic consistency between recognized text and ground truth.
*   **reason**: The specific reason for the score given by the model, used to analyze the root cause of recognition errors.

**Evaluation Report Example:**

| content | ground_truth | content_accuracy | reason |
| :--- | :--- | :--- | :--- |
| Hello, I'm here for the security guard interview. | [{"role":"USER", "ground_truth":"Hello, I'm here for the security guard interview."}] | 1.0 | The recognition result is perfectly consistent with the ground truth. |
| I am checking the monitors. | [{"role":"USER", "ground_truth":"Responsible for checking monitors in the control room."}] | 0.92 | Accurate meaning, although the wording is slightly different, core information is complete. |

---

## Prerequisites

### 1. Python Environment
It is recommended to manage two main running environments using Conda:
*   **Recognition Environment (interview)**: Used for running various ASR recognition scripts.
    *   Python 3.8+
    *   Dependencies: `dashscope`, `websocket-client`, `requests`, `pandas`, `openpyxl`
*   **Evaluation Environment (aiops)**: Used for running the accuracy evaluation of recognition results.
    *   Python 3.9+
    *   Dependencies: `deepeval`, `pandas`, `openpyxl`

### 2. Environment Variables
Before use, the following environment variables must be configured:
```bash
# Alibaba Cloud DashScope / OpenAI Proxy Key (for FunASR, Qwen-ASR)
export OPENAI_API_KEY="your-dashscope-api-key"

# iFlytek Account Information
export IFLYTEK_APP_ID="your-app-id"
export IFLYTEK_API_KEY="your-api-key"
export IFLYTEK_API_SECRET="your-api-secret"
```

### 3. G-Eval Configuration
In the evaluation environment, you need to configure the `.deepeval` directory to ensure it points to a supported LLM interface (e.g., Qwen or GPT-4) for semantic consistency scoring.

---

## How to Use

### 1. Running Individual ASR Scripts
You can directly run specific scripts to recognize a single audio file:

*   **Alibaba Cloud Fun-ASR (Non-real-time, with Speaker Diarization & Timestamps)**
    ```bash
    python scripts/asr_llm_funasr.py --wav_file data/interview_recording_1.wav
    ```
*   **Alibaba Cloud Qwen-ASR (Real-time)**
    ```bash
    python scripts/rtasr_llm_qwenasr.py --wav_file data/interview_recording_1.wav
    ```
*   **iFlytek Real-time Large Model (No Voiceprint version)**
    ```bash
    python scripts/rtasr_llm_no_voiceprint.py --wav_file data/interview_recording_1.wav
    ```

### 2. Automated Benchmark Workflow

#### Step 1: Batch Recognition
Use the automation script to traverse audio files in the dataset and record results:
```bash
# Environment: interview
python scripts/eval_asr_detect.py --dataset data/evaluation_dataset.xlsx
```
*   **Input**: `data/evaluation_dataset.xlsx` (must contain `model` and `wav_file` columns)
*   **Output**: `data/evaluation_dataset_result.xlsx`

#### Step 2: Evaluate Accuracy
Compare the recognized text with the Ground Truth and score:
```bash
# Environment: aiops
python scripts/eval_asr_accuracy.py --dataset data/evaluation_dataset_result.xlsx --filter USER
```
*   **`--filter` parameter**: Optional, used to filter specific roles in the `ground_truth` (e.g., `USER`).
*   **Output**: `data/evaluation_dataset_result_eval.xlsx`

---

## Project Structure
*   `scripts/`: Contains all ASR interface implementations and evaluation scripts.
*   `data/`: Stores test audio files, Excel datasets, and final evaluation results.
*   `references/`: Stores official ASR documentation and demos from vendors.

---

## License
This project is licensed under the [MIT License](LICENSE).
