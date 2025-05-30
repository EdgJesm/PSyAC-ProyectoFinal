import os
import shutil
from MiniGit import Sbac

def test_init_creates_repo():
    test_dir = "test_repo"
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)

    os.mkdir(test_dir)
    sbac = Sbac(test_dir)
    result = sbac.init()

    assert result is True
    assert os.path.isdir(os.path.join(test_dir, ".sbac"))
    assert os.path.isfile(os.path.join(test_dir, ".sbac", "sbac.db"))

    shutil.rmtree(test_dir)
