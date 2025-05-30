import os
import shutil
from MiniGit import Sbac

def test_commit_file():
    test_dir = "test_repo_commit"
    os.makedirs(test_dir, exist_ok=True)
    with open(os.path.join(test_dir, "file.txt"), "w") as f:
        f.write("commit test")

    sbac = Sbac(test_dir)
    sbac.init()
    sbac.add("file.txt")
    result = sbac.commit("Test commit")
    assert result is True

    shutil.rmtree(test_dir)
