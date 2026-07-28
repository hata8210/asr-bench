# -*- encoding:utf-8 -*-
import pandas as pd
import json
import argparse
import os
import sys

# Since deepeval is in aiops environment, this script should be run in that environment.
try:
    from deepeval.test_case import LLMTestCase, SingleTurnParams
    from deepeval.metrics import GEval
except ImportError:
    print("Error: deepeval not found. Please run this script in the 'aiops' environment.")
    sys.exit(1)

# Criteria from scripts/test_gval.py
CRITERIA = """
请仔细对比 actual_output 与 expected_output 这两段文字。
提取文字信息，计算两者在文字信息上一致的信息占总文字信息的百分比。
准确率要求较高，对意思不一致的字词惩罚需要严厉。
记住不区分繁体和简体,以0-1的浮点数输出正确占比。
判断分两步骤：
1.判断 expected_output 文字内容是否都在 actual_output中出现
2.判断actual_output是否出现一些不属于expected_output的文字内容
"""

def parse_ground_truth(json_str, role_filter=None):
    """解析 ground_truth JSON 字符串并根据 role 过滤"""
    try:
        # 有些可能是浮点数（NaN）
        if pd.isna(json_str) or not isinstance(json_str, str):
            return ""
        data = json.loads(json_str)
        if role_filter:
            texts = [item['ground_truth'] for item in data if item.get('role') == role_filter]
        else:
            texts = [item['ground_truth'] for item in data]
        return "\n".join(texts)
    except Exception as e:
        print(f"解析 ground_truth 出错: {e}")
        return ""

def main():
    parser = argparse.ArgumentParser(description="评估 ASR 识别准确率")
    parser.add_argument("--dataset", type=str, required=True, help="输入 Excel 文件路径")
    parser.add_argument("--filter", type=str, default=None, help="ground_truth 中的角色过滤 (例如 USER)")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"错误: 文件 {args.dataset} 不存在")
        sys.exit(1)

    print(f"读取数据集: {args.dataset}")
    df = pd.read_excel(args.dataset)

    # 检查必要的列
    if 'ground_truth' not in df.columns or 'content' not in df.columns:
        print("错误: Excel 文件中缺少 'ground_truth' 或 'content' 列")
        sys.exit(1)

    # 初始化结果列
    df['content_accuracy'] = 0.0
    df['reason'] = ""

    # 定义度量指标
    metric = GEval(
        name="Accuracy",
        criteria=CRITERIA,
        evaluation_params=[SingleTurnParams.ACTUAL_OUTPUT, SingleTurnParams.EXPECTED_OUTPUT],
        threshold=0.0 # 我们只需要分数，不需要判定通过
    )

    total = len(df)
    for index, row in df.iterrows():
        print(f"[{index+1}/{total}] 正在评估识别结果...")
        
        expected_output = parse_ground_truth(row['ground_truth'], role_filter=args.filter)
        actual_output = str(row['content']) if not pd.isna(row['content']) else ""

        if not expected_output:
            print(f"警告: 第 {index+1} 行预期的地标文字(ground_truth)为空，跳过评估。")
            continue

        test_case = LLMTestCase(
            input="语音识别评估",
            actual_output=actual_output,
            expected_output=expected_output
        )

        print("-" * 20 + " Evaluation Details " + "-" * 20)
        print(f"Expected Output (Ground Truth):\n{expected_output}")
        print(f"\nActual Output (ASR Content):\n{actual_output}")
        print("-" * 60)

        try:
            metric.measure(test_case)
            score = metric.score
            reason = metric.reason
            
            df.at[index, 'content_accuracy'] = score
            df.at[index, 'reason'] = reason
            
            print(f"得分: {score}")
        except Exception as e:
            print(f"评估过程中出错: {e}")
            df.at[index, 'reason'] = f"评估异常: {str(e)}"

    # 生成输出文件名
    base, ext = os.path.splitext(args.dataset)
    output_file = f"{base}_eval{ext}"
    
    print(f"保存评估结果到: {output_file}")
    df.to_excel(output_file, index=False)
    print("评估完成。")

if __name__ == "__main__":
    main()
