import re
from pathlib import Path

problems = 0

for f in sorted(Path("templates").glob("*.html")):
    html = f.read_text(encoding="utf-8")

    # 1. Har POST form me csrf_token hona chahiye
    forms = re.findall(r"<form\b.*?</form>", html, flags=re.S | re.I)
    for i, form in enumerate(forms, 1):
        opening = re.match(r"<form\b[^>]*>", form, flags=re.S | re.I).group(0)
        if re.search(r'method\s*=\s*["\']?post', opening, re.I):
            if "csrf_token" in form:
                print(f"✅ {f.name} - form #{i}")
            else:
                print(f"❌ {f.name} - form #{i}: csrf_token MISSING")
                problems += 1

    # 2. {% if %}, {% for %}, {% with %}, {% block %} sab band hone chahiye
    for tag in ("if", "for", "with", "block"):
        opens = len(re.findall(r"\{%-?\s*" + tag + r"\b", html))
        closes = len(re.findall(r"\{%-?\s*end" + tag + r"\b", html))
        if opens != closes:
            print(f"❌ {f.name}: {{% {tag} %}} {opens} baar khula, {closes} baar band")
            problems += 1

print()
print("🎉 Sab theek hai!" if problems == 0 else f"⚠️ {problems} problem(s) mili, upar dekho.")