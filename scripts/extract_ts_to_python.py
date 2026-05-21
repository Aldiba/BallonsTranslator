"""
Extract translations from .ts XML files and generate Python dict files.
Usage: python scripts/extract_ts_to_python.py
"""
import os, sys, xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSLATE_DIR = os.path.join(PROJECT_DIR, 'translate')
OUTPUT_DIR = os.path.join(TRANSLATE_DIR, 'i18n')


def extract_ts(filepath):
    """Parse a .ts file and return {context: {source: translation}}."""
    tree = ET.parse(filepath)
    root = tree.getroot()
    result = {}
    for context in root.findall('context'):
        name = context.find('name').text
        messages = {}
        for msg in context.findall('message'):
            source = msg.find('source')
            if source is None or not source.text:
                continue
            source_text = source.text
            trans_elem = msg.find('translation')
            if trans_elem is not None and trans_elem.text:
                messages[source_text] = trans_elem.text
            else:
                messages[source_text] = ""
        result[name] = messages
    return result


def generate_py_file(lang_code, data):
    """Generate a Python file with the TRANSLATIONS dict."""
    lines = ["# Auto-generated from .ts files", "TRANSLATIONS = {"]
    for context_name in sorted(data.keys()):
        messages = data[context_name]
        lines.append(f"    {repr(context_name)}: {{")
        for source in sorted(messages.keys()):
            translation = messages[source]
            trans_repr = repr(translation) if translation else '""'
            lines.append(f"        {repr(source)}: {trans_repr},")
        lines.append("    },")
    lines.append("}\n")
    return "\n".join(lines)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Write __init__.py
    init_lines = [
        "# -*- coding: utf-8 -*-",
        '"""Translation data package. Auto-generated. Do not edit manually."""',
        "import os",
        "import importlib",
        "",
        "LANG_DATA = {}",
        "",
        "def load_all():",
        '    """Dynamically import all translation modules in this package."""',
        '    package_dir = os.path.dirname(__file__)',
        "    LANG_DATA.clear()",
        "    for fname in sorted(os.listdir(package_dir)):",
        '        if fname.endswith(".py") and fname != "__init__.py":',
        "            lang_code = fname[:-3]",
        '            mod = importlib.import_module(f".{lang_code}", __package__)',
        "            LANG_DATA[lang_code] = getattr(mod, 'TRANSLATIONS', {})",
        "",
        "def get_available_codes():",
        '    """Return list of available language codes."""',
        "    return sorted(LANG_DATA.keys())",
        "",
    ]
    with open(os.path.join(OUTPUT_DIR, '__init__.py'), 'w', encoding='utf-8') as f:
        f.write("\n".join(init_lines))

    # Process each .ts file
    for fname in sorted(os.listdir(TRANSLATE_DIR)):
        if not fname.endswith('.ts'):
            continue
        filepath = os.path.join(TRANSLATE_DIR, fname)
        lang_code = fname[:-3]  # remove ".ts"

        data = extract_ts(filepath)
        py_content = generate_py_file(lang_code, data)

        outpath = os.path.join(OUTPUT_DIR, f"{lang_code}.py")
        with open(outpath, 'w', encoding='utf-8') as f:
            f.write(py_content)
        print(f"  Generated: {lang_code}.py  ({sum(len(v) for v in data.values())} entries, {len(data)} contexts)")

    print(f"\nOutput directory: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
