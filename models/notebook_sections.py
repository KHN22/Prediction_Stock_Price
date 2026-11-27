"""Locate executable notebook sections by content, independent of cell order."""
import json


def load_sections(path, markers):
    cells = json.loads(path.read_text(encoding="utf-8"))["cells"]
    code = ["".join(cell.get("source", [])) for cell in cells
            if cell.get("cell_type") == "code"]
    sections = {}
    for role, tokens in markers.items():
        matches = [source for source in code if all(token in source for token in tokens)]
        if len(matches) != 1:
            raise ValueError(
                f"{path.name}: ส่วน notebook {role} ต้องตรงกับ code cell เดียว "
                f"แต่พบ {len(matches)} เซลล์ กรุณาตรวจสอบโครงสร้าง notebook"
            )
        sections[role] = matches[0]
    return sections
