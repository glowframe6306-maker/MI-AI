import importlib, importlib.util
try:
    spec = importlib.util.find_spec('google.genai')
    print('google.genai present:', bool(spec))
except Exception as e:
    print('google.genai present: error', e)

try:
    spec2 = importlib.util.find_spec('google.generativeai')
    print('google.generativeai present:', bool(spec2))
except Exception as e:
    print('google.generativeai present: error', e)

try:
    import importlib.metadata as importlib_metadata
    v = importlib_metadata.version('google-genai')
    print('google-genai version:', v)
except Exception as e:
    print('google-genai version: error', type(e).__name__, e)

try:
    v2 = importlib_metadata.version('google-generativeai')
    print('google-generativeai version:', v2)
except Exception as e:
    print('google-generativeai version: not installed')
