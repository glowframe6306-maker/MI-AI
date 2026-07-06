from pathlib import Path
from shutil import copyfile
src = Path('images/logo.png')
dst = Path('frontend/images/logo.png')
dst.parent.mkdir(parents=True, exist_ok=True)
copyfile(src, dst)
print(src.exists(), src.resolve())
print(dst.exists(), dst.resolve())
print(dst.stat().st_size)
