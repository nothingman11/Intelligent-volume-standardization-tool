import os
import sys
import time
import shutil
from pathlib import Path

# ================= 配置区域 (可根据需要微调) =================
# 源文件夹 (箫的原始音频)
SOURCE_DIR = r"G:\Chinese Xiao\Xiao C"
# 目标文件夹 (处理后的音频)
TARGET_DIR = r"D:\new\Xiao C"

# 【关键】目标音量 (dBFS)
# 箫的动态大，-20太轻，-10易破音。-15 是最佳平衡点。
TARGET_DBFS = -15.0 

# 【关键】安全峰值限制 (dBFS)
# 无论怎么放大，输出文件的最高峰值绝不允许超过这个值，防止破音
MAX_PEAK_LIMIT = -1.0 

# 跳过阈值：如果文件平均音量已经高于此值，认为合格，直接复制
# 设为 -25.0，意味着比 -25 响的都直接过，只处理特别轻的
SKIP_THRESHOLD = -25.0 

# 支持的音频格式
SUPPORTED_EXTS = {'.wav', '.mp3', '.flac', '.m4a', '.aac', '.ogg', '.wma'}
# ===========================================================

try:
    from pydub import AudioSegment
except ImportError:
    print("❌ 错误：未安装 pydub。请运行: python -m pip install pydub")
    sys.exit(1)

def setup_ffmpeg():
    """强制锁定桌面目录下的 ffmpeg.exe"""
    script_dir = Path(__file__).parent.resolve()
    ffmpeg_path = script_dir / "ffmpeg.exe"
    
    if not ffmpeg_path.exists():
        print(f"⚠️ 警告：未在脚本目录找到 ffmpeg.exe")
        print(f"   路径应为: {ffmpeg_path}")
        print("   将尝试使用系统环境变量中的 ffmpeg，可能会慢或失败。")
        return False
    
    # 覆盖 pydub 的查找逻辑
    import pydub.utils
    def custom_which(program):
        if program == 'ffmpeg':
            return str(ffmpeg_path)
        # 兼容 avconv
        if program == 'avconv':
            return str(ffmpeg_path)
        return None # 强制只用 ffmpeg
    
    pydub.utils.which = custom_which
    print(f"✅ 已锁定 FFmpeg: {ffmpeg_path}")
    return True

def get_files_to_process(root_path):
    """扫描所有音频文件"""
    files = []
    root = Path(root_path)
    if not root.exists():
        return files
    
    # 递归查找
    for p in root.rglob('*'):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS:
            if not p.name.startswith('._'): 
                files.append(p)
    return sorted(files) # 排序以保证顺序一致

def process_single_audio(input_path, output_path, target_db, max_peak, skip_thresh):
    """
    核心处理逻辑：
    1. 检查是否存在 (断点续传)
    2. 检查音量 (智能跳过)
    3. 计算增益 (带防破音保护)
    4. 导出
    """
    try:
        # 1. 断点续传检查
        if output_path.exists() and output_path.stat().st_size > 0:
            return True, "Skipped (Exists)"

        # 创建目录
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 2. 加载音频
        audio = AudioSegment.from_file(str(input_path))
        
        # 获取当前参数
        current_dbfs = audio.dBFS
        current_peak = audio.max_dBFS
        
        # 3. 智能跳过判断
        # 如果平均音量已经大于阈值，且峰值没有超标，直接复制
        if current_dbfs >= skip_thresh:
            # 额外检查：如果虽然平均音量够，但峰值已经爆了(>0)，还是得处理一下限幅
            if current_peak <= max_peak:
                shutil.copy2(str(input_path), str(output_path))
                return True, f"Skipped (Vol OK: {current_dbfs:.1f}dB)"

        # 4. 计算所需增益
        gain_needed = target_db - current_dbfs
        
        # 5. 【关键】防破音保护逻辑
        # 预测提升后的峰值
        predicted_peak = current_peak + gain_needed
        
        if predicted_peak > max_peak:
            # 如果会破音，减少增益，让峰值刚好卡在 max_peak
            safe_gain = max_peak - current_peak
            # 记录实际应用的增益（可能小于目标增益）
            actual_gain = safe_gain
            # print(f"   [Limit] Clip prevented: {gain_needed:.1f} -> {actual_gain:.1f}")
        else:
            actual_gain = gain_needed

        # 6. 应用增益
        # 如果增益太小(<0.1dB)，也直接复制，避免无谓的重编码
        if abs(actual_gain) < 0.1:
             shutil.copy2(str(input_path), str(output_path))
             return True, f"Skipped (No Change Needed)"
             
        louder_audio = audio.apply_gain(actual_gain)
        
        # 7. 导出 (保持原格式)
        fmt = input_path.suffix.lower().replace('.', '')
        # pydub 特殊格式映射
        if fmt == 'm4a': fmt = 'ipod'
        if fmt == 'aa': fmt = 'aac'
        if fmt == 'wma': fmt = 'wmv' # 某些版本需要
        
        louder_audio.export(str(output_path), format=fmt)
        
        msg = f"Done (+{actual_gain:.1f}dB)"
        if predicted_peak > max_peak:
            msg += " [Limited]"
            
        return True, msg

    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    print("="*70)
    print("🎋 箫演奏技法音频 · 智能音量标准化工具 (防破音版)")
    print("="*70)
    
    # 初始化
    setup_ffmpeg()
    
    print(f"📂 源目录 : {SOURCE_DIR}")
    print(f"📂 目标目录: {TARGET_DIR}")
    print(f"🎯 目标音量: {TARGET_DBFS} dBFS (平均)")
    print(f"🛡️ 峰值限制: {MAX_PEAK_LIMIT} dBFS (绝对上限，防破音)")
    print(f"⏭️  跳过阈值: {SKIP_THRESHOLD} dBFS (高于此值直接复制)")
    print("-" * 70)

    if not os.path.exists(SOURCE_DIR):
        print(f"❌ 错误：源目录不存在！请检查: {SOURCE_DIR}")
        sys.exit(1)

    # 扫描
    print("🔍 正在扫描文件...")
    file_list = get_files_to_process(SOURCE_DIR)
    total = len(file_list)
    
    if total == 0:
        print("❌ 未找到任何音频文件。")
        sys.exit(0)
    
    print(f"📦 共发现 {total} 个文件。开始处理...\n")

    # 统计
    success = 0
    skipped = 0
    errors = 0
    
    start_time = time.time()
    
    for i, src in enumerate(file_list):
        rel = src.relative_to(SOURCE_DIR)
        dst = Path(TARGET_DIR) / rel
        
        ok, msg = process_single_audio(src, dst, TARGET_DBFS, MAX_PEAK_LIMIT, SKIP_THRESHOLD)
        
        if ok:
            if "Skipped" in msg:
                skipped += 1
            else:
                success += 1
        else:
            errors += 1
            print(f"[{i+1}/{total}] ❌ {src.name}: {msg}")
            continue
        
        # 进度汇报 (每 50 个或最后)
        if (i + 1) % 50 == 0 or (i + 1) == total:
            elapsed = time.time() - start_time
            speed = (i + 1) / elapsed if elapsed > 0 else 0
            pct = ((i + 1) / total) * 100
            print(f"⏳ [{i+1}/{total}] {pct:.1f}% | 速度:{speed:.1f}个/s | 成功:{success} 跳过:{skipped} 错:{errors}")

    # 总结
    total_time = time.time() - start_time
    print("\n" + "="*70)
    print("🎉 处理完成！")
    print(f"⏱️  总耗时 : {total_time:.2f} 秒")
    print(f"✅ 成功处理: {success} 个 (音量已提升)")
    print(f"⏭️  智能跳过: {skipped} 个 (音量达标或已存在)")
    print(f"💥 失败数量: {errors} 个")
    print(f"📁 结果保存: {TARGET_DIR}")
    print("="*70)

if __name__ == "__main__":
    main()