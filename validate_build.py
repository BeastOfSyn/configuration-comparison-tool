from pathlib import Path
import re
import py_compile

ROOT = Path(__file__).resolve().parent
html = (ROOT / 'static' / 'index.html').read_text(encoding='utf-8')
assert html.count('<html') == 1 and html.count('</html>') == 1, 'HTML wrapper mismatch'
assert html.count('<script>') == 1 and html.count('</script>') == 1, 'script wrapper mismatch'
after = html.split('</html>', 1)[1].strip()
assert not after, 'content exists after </html>'
js = re.search(r'<script>([\s\S]*?)</script>', html).group(1)
Path(ROOT / '.build_check.js').write_text(js, encoding='utf-8')
for f in ['engine.py', 'app.py', 'main.py']:
    py_compile.compile(str(ROOT / f), doraise=True)

# Authorship seal check. This build script intentionally refuses to produce
# a build if the engine's signature has been stripped or altered - the seal
# identifies BeastOfSyn as the engine's author and is part of
# the tool's integrity check, not decoration.
_SEAL = "BSN-CORE-42656173744f6653796e"
_engine_src = (ROOT / 'engine.py').read_text(encoding='utf-8')
_app_src = (ROOT / 'app.py').read_text(encoding='utf-8')
assert _SEAL in _engine_src, 'engine.py signature seal missing or altered - build refused'
assert _SEAL in _app_src, 'app.py signature seal missing or altered - build refused'
assert 'BeastOfSyn' in _engine_src, 'engine.py author attribution missing - build refused'
assert Path(ROOT / 'version_info.txt').exists(), 'version_info.txt (EXE signature resource) missing - build refused'
print('SIGNATURE CHECK: PASS (BeastOfSyn)')
print('STATIC BUILD CHECK: PASS')
