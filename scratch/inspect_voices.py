import pickle
import numpy as np
import os

voices_path = r"d:\JARVIS M7\models\voices-v1.0.bin"
print("File size:", os.path.getsize(voices_path))

# Try numpy
try:
    data = np.load(voices_path, allow_pickle=True)
    print("Numpy load success!")
    print("Type:", type(data))
    if hasattr(data, "files"):
        print("Files:", data.files)
    elif isinstance(data, dict):
        print("Keys:", sorted(data.keys()))
    else:
        print("Shape/Length:", len(data))
except Exception as e:
    print("Numpy load failed:", e)

# Try pickle
try:
    with open(voices_path, "rb") as f:
        data = pickle.load(f)
    print("Pickle load success!")
    print("Type:", type(data))
    if isinstance(data, dict):
        print("Keys:", sorted(data.keys()))
    else:
        print("Length:", len(data))
except Exception as e:
    print("Pickle load failed:", e)
