import os
import shutil
from MiniGit import Sbac

def test_add_file():
    test_dir = "test_repo_add"
    os.makedirs(test_dir, exist_ok=True)
    with open(os.path.join(test_dir, "file.txt"), "w") as f:
        f.write("contenido de prueba")

    sbac = Sbac(test_dir)
    sbac.init()
    result = sbac.add("file.txt")
    assert result is True

    shutil.rmtree(test_dir)
