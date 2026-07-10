import os
import urllib.request
import sys

def download_file(url, dest_path):
    print(f"Downloading {url} to {dest_path}...")
    
    def report_hook(block_num, block_size, total_size):
        read_so_far = block_num * block_size
        if total_size > 0:
            percent = read_so_far * 1e2 / total_size
            s = f"\rProgress: {percent:5.1f}% [{read_so_far // 1024 // 1024}MB / {total_size // 1024 // 1024}MB]"
            sys.stdout.write(s)
            sys.stdout.flush()
        else:
            sys.stdout.write(f"\rDownloaded {read_so_far // 1024 // 1024}MB")
            sys.stdout.flush()

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    urllib.request.urlretrieve(url, dest_path, reporthook=report_hook)
    print("\nDownload complete.")

if __name__ == "__main__":
    model_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
    voices_url = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
    
    models_dir = r"d:\JARVIS M7\models"
    model_dest = os.path.join(models_dir, "kokoro-v1.0.onnx")
    voices_dest = os.path.join(models_dir, "voices-v1.0.bin")
    
    download_file(model_url, model_dest)
    download_file(voices_url, voices_dest)
