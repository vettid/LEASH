"""Build LEASH-Position-Paper.docx from README.md.

Usage: python3 tools/build-docx.py [README.md] [LEASH-Position-Paper.docx]
Needs pandoc and python-docx (pip install python-docx).
"""
import sys, re, subprocess, tempfile
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

src = sys.argv[1] if len(sys.argv) > 1 else 'README.md'
out = sys.argv[2] if len(sys.argv) > 2 else 'LEASH-Position-Paper.docx'
work = tempfile.mkdtemp()
subprocess.run(['pandoc', '-o', work + '/default-ref.docx', '--print-default-data-file', 'reference.docx'], check=True)
s = open(src).read()
s = s.replace(':white_check_mark:', '✓').replace(':x:', '✗')
s = s.replace('](LICENSE)', '](https://github.com/vettid/LEASH/blob/main/LICENSE)')
# The first heading, tagline and one-line description become the title block.
head = "# LEASH\n\n**Lightweight Encrypted Agent Secret Handling**\n\nA position paper proposing a companion security model for agent tool use\n"
assert s.startswith(head), "README opening changed"
s = s[len(head):]
m = re.search(r'\*\*Version\*\* \| ([^|]+?) \|', s)
version = m.group(1).strip()
open(work + '/paper.md', 'w').write(s)

# Reference document: pandoc's default styles, plus a header and a page-number footer.
ref = Document(work + '/default-ref.docx')
sec = ref.sections[0]
sec.left_margin = sec.right_margin = Cm(2.2)
sec.top_margin = sec.bottom_margin = Cm(2.3)
def small(p, text=None):
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text) if text else p.add_run()
    r.font.size = Pt(8); r.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
    return r
small(sec.header.paragraphs[0], 'LEASH — Position Paper — v' + version)
r = small(sec.footer.paragraphs[0], 'Page ')
r2 = small(sec.footer.paragraphs[0])
for t, txt in (('begin', None), (None, 'PAGE'), ('end', None)):
    if t:
        e = OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'), t)
    else:
        e = OxmlElement('w:instrText'); e.set(qn('xml:space'), 'preserve'); e.text = txt
    r2._r.append(e)
for name, size in (('Normal', 10.5), ('Body Text', 10.5), ('First Paragraph', 10.5), ('Compact', 9)):
    try: ref.styles[name].font.size = Pt(size)
    except KeyError: pass
ref.save(work + '/ref.docx')

subprocess.run(['pandoc', work + '/paper.md', '-f', 'gfm', '-t', 'docx', '--reference-doc=' + work + '/ref.docx',
    '-M', 'title=LEASH', '-M', 'subtitle=Lightweight Encrypted Agent Secret Handling',
    '-M', 'abstract-title=', '-o', out], check=True)

d = Document(out)
# The one-line description under the subtitle.
sub = [p for p in d.paragraphs if p.style.name == 'Subtitle'][0]
new = OxmlElement('w:p'); sub._p.addnext(new)
from docx.text.paragraph import Paragraph
desc = Paragraph(new, sub._parent); desc.alignment = WD_ALIGN_PARAGRAPH.CENTER
rr = desc.add_run('A position paper proposing a companion security model for agent tool use'); rr.italic = True
# Tables: full width, visible grid, smaller text; repeat the header row.
for t in d.tables:
    t.style = d.styles['Table'] if 'Table' in [x.name for x in d.styles] else t.style
    tblPr = t._tbl.tblPr
    b = OxmlElement('w:tblBorders')
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        e = OxmlElement('w:' + edge); e.set(qn('w:val'), 'single'); e.set(qn('w:sz'), '4'); e.set(qn('w:color'), 'BBBBBB'); b.append(e)
    tblPr.append(b)
    wide = len(t.columns) >= 6
    w = tblPr.find(qn('w:tblW'))
    if w is None:
        w = OxmlElement('w:tblW'); tblPr.append(w)
    w.set(qn('w:type'), 'pct'); w.set(qn('w:w'), '5000')
    if all(c.text.strip() == '' for c in t.rows[0].cells):
        t._tbl.remove(t.rows[0]._tr)
    for row in t.rows:
        for c in row.cells:
            for p in c.paragraphs:
                for r in p.runs: r.font.size = Pt(7.5 if wide else 9)
cp = d.core_properties
cp.title = 'LEASH: Lightweight Encrypted Agent Secret Handling'; cp.author = 'Al Liebl'
cp.subject = 'Position paper, version ' + version; cp.comments = 'Generated from README.md of github.com/vettid/LEASH'
d.save(out)
print('version', version, 'tables', len(d.tables))
