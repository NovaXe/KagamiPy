import os
import subprocess
import platform


start_script = "java -jar Lavalink.jar"
system = platform.system()
if system == "Windows":
    shell_name = os.getenv("SHELL", "powershell")
    subprocess.run([shell_name, "-command", start_script], check=True)
elif system == "Linux" or system == "Darwin":
    shell_name = os.getenv("SHELL", "/bin/bash")
    subprocess.run([shell_name, "-c", start_script], check=True)
else:
    raise RuntimeError(f"Unsupported opperating system: {system}")
