import sys; sys.path.insert(0,'src')
from langcheck import english_windows
print("GATE", english_windows(sys.argv[1], skip_start=10, skip_end=25))
