import os
from moviepy import AudioFileClip, concatenate_audioclips

def merge_m4a_to_wav(file1, file2, output_file):
    print(f"Loading {file1}...")
    clip1 = AudioFileClip(file1)
    print(f"Loading {file2}...")
    clip2 = AudioFileClip(file2)
    
    print("Concatenating clips...")
    final_clip = concatenate_audioclips([clip1, clip2])
    
    print(f"Writing to {output_file}...")
    # 在导出阶段统一指定采样率和声道
    final_clip.write_audiofile(output_file, fps=16000, nbytes=2, ffmpeg_params=["-ac", "1"], codec='pcm_s16le')
    
    clip1.close()
    clip2.close()
    final_clip.close()

if __name__ == "__main__":
    file1 = "data/金赋5.m4a"
    file2 = "data/金赋6.m4a"
    output = "data/金赋合并.wav"
    
    if not os.path.exists("data"):
        os.makedirs("data")
        
    merge_m4a_to_wav(file1, file2, output)
    print("Done!")
