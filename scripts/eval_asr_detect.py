# -*- encoding:utf-8 -*-
import pandas as pd
import subprocess
import argparse
import os
import datetime
import re
import time

def run_asr_model(model_script, wav_file):
    """
    运行指定的 ASR 脚本，实时显示日志并捕获最终结果。
    通用逻辑，不针对特定供应商进行重试或补救。
    """
    if not os.path.exists(model_script):
        return f"错误: 脚本 {model_script} 不存在"
    if not os.path.exists(wav_file):
        return f"错误: 音频文件 {wav_file} 不存在"

    cmd = ["python3", "-u", model_script, "--wav_file", wav_file]
    print(f"正在运行: {' '.join(cmd)}")
    
    full_output = []
    try:
        env = os.environ.copy()
        env["no_proxy"] = "*"
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            env=env,
            bufsize=1
        )
        
        start_time = time.time()
        timeout = 600 
        
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                print(f"  [LOG] {line.strip()}")
                full_output.append(line)
            
            if time.time() - start_time > timeout:
                process.terminate()
                return "执行超时"
        
        output = "".join(full_output)
        
        if process.returncode != 0:
            # 如果运行失败，将错误日志的最后两行存入 content
            lines = [l.strip() for l in output.split('\n') if l.strip()]
            err_msg = " | ".join(lines[-2:]) if len(lines) >= 2 else (lines[-1] if lines else "未知错误")
            return f"执行失败: {err_msg}"
        
        # 提取识别结果
        pattern = r"==================== (?:识别结果|完整识别结果) ====================\s*(.*?)\s*======================================================"
        match = re.search(pattern, output, re.DOTALL)
        if match:
            return match.group(1).strip()
        else:
            # 回退策略
            lines = [l.strip() for l in output.split('\n') if l.strip()]
            return lines[-1] if lines else "无输出"
                
    except Exception as e:
        return f"异常: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description="ASR 自动化评估工具")
    parser.add_argument("--dataset", type=str, required=True, help="Excel 评估数据集路径")
    args = parser.parse_args()

    if not os.path.exists(args.dataset):
        print(f"错误: 文件 {args.dataset} 不存在")
        return

    print(f"读取数据集: {args.dataset}")
    df = pd.read_excel(args.dataset)

    # 生成输出文件名：在原文件名后增加 _result 后缀
    file_base, file_ext = os.path.splitext(args.dataset)
    output_dataset = f"{file_base}_result{file_ext}"
    print(f"评估结果将保存至: {output_dataset}")

    # 检查必要的列
    required_columns = ['model', 'wav_file']
    for col in required_columns:
        if col not in df.columns:
            print(f"错误: Excel 文件中缺少 '{col}' 列")
            return

    # 确保 content 和 eval_time 列存在并强制转换为字符串类型，避免 pandas 的类型推断警告
    if 'content' not in df.columns:
        df['content'] = ""
    else:
        df['content'] = df['content'].astype(str)

    if 'eval_time' not in df.columns:
        df['eval_time'] = ""
    else:
        df['eval_time'] = df['eval_time'].astype(str)

    for index, row in df.iterrows():
        model_script = row['model']
        wav_file = row['wav_file']
        
        print(f"[{index+1}/{len(df)}] 处理文件: {wav_file} (使用模型: {model_script})")
        
        content = run_asr_model(model_script, wav_file)
        eval_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        df.at[index, 'content'] = content
        df.at[index, 'eval_time'] = eval_time
        
        # 实时保存，防止崩溃导致数据丢失
        print(f"  [DEBUG] 正在保存结果到: {output_dataset}")
        df.to_excel(output_dataset, index=False)
        print(f"已更新结果至 {output_dataset}。")

    print(f"\n评估完成。结果已保存至: {output_dataset}")

if __name__ == "__main__":
    main()
