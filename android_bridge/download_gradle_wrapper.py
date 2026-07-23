import urllib.request
import os

files = {
    "https://raw.githubusercontent.com/gradle/gradle/v8.0.0/gradlew.bat": "gradlew.bat",
    "https://raw.githubusercontent.com/gradle/gradle/v8.0.0/gradlew": "gradlew",
    "https://raw.githubusercontent.com/gradle/gradle/v8.0.0/gradle/wrapper/gradle-wrapper.jar": "gradle/wrapper/gradle-wrapper.jar"
}

os.makedirs("gradle/wrapper", exist_ok=True)

for url, target in files.items():
    print(f"Downloading {url} to {target}...")
    try:
        urllib.request.urlretrieve(url, target)
        print("Success.")
    except Exception as e:
        print(f"Failed: {e}")
