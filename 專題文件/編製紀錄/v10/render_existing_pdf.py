from pathlib import Path
import importlib.util
import shutil
import sys

pdf = Path(sys.argv.pop(1)).resolve()
# 第一個參數為 PDF，第二個參數為目前可用的 render_docx.py 絕對路徑。
skill = Path(sys.argv.pop(1)).resolve()
spec = importlib.util.spec_from_file_location('packaged_renderer', skill)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)

def use_pdf(doc_path, user_profile, convert_tmp_dir, stem, verbose):
    out = Path(convert_tmp_dir) / (stem + '.pdf')
    shutil.copyfile(pdf, out)
    return str(out), 'Microsoft Word COM 實際排版 PDF'

renderer.convert_to_pdf = use_pdf
renderer.main()
