"""多步 SMILES → 反应路径 / 路径对比 PNG。

支持三种输入（无需分子通用名）:

1) 中间体序列（用 -> 或 => 连接）:
   CCO -> CC=O -> CC(=O)O

2) 反应式逐步（每行一步，RDKit reaction SMILES）:
   CCO.CC(=O)O>>CCOC(=O)C
   CCOC(=O)C>>CC(=O)O

3) 多条路径对比（路径之间用空行，或 JSON）:
   # route A
   CCO -> CC=O -> CC(=O)O

   # route B
   CCO -> CCOC(=O)C -> CC(=O)O

用法:
  .\\.venv\\Scripts\\python.exe draw_pathway.py "CCO -> CC=O -> CC(=O)O"
  .\\.venv\\Scripts\\python.exe draw_pathway.py -f routes.txt -o outputs/compare.png
  .\\.venv\\Scripts\\python.exe draw_pathway.py --demo
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont
from rdkit import Chem
from rdkit.Chem import AllChem, Draw


ARROW = "→"
STEP_GAP = 16
ROUTE_GAP = 28
PAD = 24


@dataclass
class Step:
    """单步：要么是分子序列中的一个分子，要么是一条反应。"""

    molecules: List[Chem.Mol] = field(default_factory=list)
    reaction: Optional[AllChem.ChemicalReaction] = None
    label: str = ""
    raw: str = ""


@dataclass
class Route:
    name: str
    steps: List[Step]
    note: str = ""


def _mol_from_smiles(smi: str) -> Chem.Mol:
    mol = Chem.MolFromSmiles(smi.strip())
    if mol is None:
        raise ValueError(f"无法解析 SMILES: {smi!r}")
    return mol


def _is_reaction_line(text: str) -> bool:
    """判断是否为反应式（A>>B 或 A>reagent>B），排除分子序列里的 -> / =>。"""
    if ">>" in text:
        return True
    # 去掉路径箭头后再数 '>'，避免 "CCO -> CC=O" 被误判
    normalized = re.sub(r"->|=>|→|⟶", " ", text)
    return normalized.count(">") >= 2


def parse_step(text: str, label: str = "") -> Step:
    text = text.strip()
    if not text:
        raise ValueError("空步骤")

    if _is_reaction_line(text):
        try:
            rxn = AllChem.ReactionFromSmarts(text, useSmiles=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"无法解析反应式: {text!r} ({exc})") from exc
        if rxn is None:
            raise ValueError(f"无法解析反应式: {text!r}")
        return Step(reaction=rxn, label=label, raw=text)

    mol = _mol_from_smiles(text)
    return Step(molecules=[mol], label=label, raw=text)


def parse_molecule_sequence(line: str, route_name: str = "Route") -> Route:
    """CCO -> CC=O -> CC(=O)O"""
    parts = re.split(r"\s*(?:->|=>|→|⟶)\s*", line.strip())
    parts = [p for p in parts if p]
    if len(parts) < 2:
        raise ValueError(
            f"分子序列至少需要 2 个结构（用 -> 连接）: {line!r}"
        )
    steps = [
        parse_step(p, label=f"S{i+1}" if i < len(parts) - 1 else "Product")
        for i, p in enumerate(parts)
    ]
    # 中间体命名：S1, S2, ..., Product
    for i, step in enumerate(steps):
        if i == 0:
            step.label = "Start"
        elif i == len(steps) - 1:
            step.label = "Product"
        else:
            step.label = f"Int-{i}"
    return Route(name=route_name, steps=steps)


def parse_routes_text(text: str) -> List[Route]:
    """解析文本：空行分隔多条路径；# 开头为路径名/注释。"""
    blocks = re.split(r"\n\s*\n", text.strip())
    routes: List[Route] = []

    for bi, block in enumerate(blocks):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue

        name = f"Route {bi + 1}"
        note = ""
        body: List[str] = []
        for ln in lines:
            if ln.startswith("#"):
                title = ln.lstrip("#").strip()
                if title.lower().startswith("note:"):
                    note = title[5:].strip()
                elif not body:
                    name = title or name
                else:
                    note = title
            else:
                body.append(ln)

        if not body:
            continue

        # 单行且含箭头 → 分子序列
        if len(body) == 1 and re.search(r"->|=>|→|⟶", body[0]) and not _is_reaction_line(
            body[0]
        ):
            route = parse_molecule_sequence(body[0], route_name=name)
            route.note = note
            routes.append(route)
            continue

        # 多行：每行一步（分子或反应）
        steps: List[Step] = []
        for i, ln in enumerate(body):
            if re.search(r"->|=>|→|⟶", ln) and not _is_reaction_line(ln):
                # 一行内写了整条序列
                sub = parse_molecule_sequence(ln, route_name=name)
                steps.extend(sub.steps)
            else:
                label = f"Step {i + 1}"
                steps.append(parse_step(ln, label=label))
        routes.append(Route(name=name, steps=steps, note=note))

    if not routes:
        raise ValueError("未解析到任何路径，请检查输入格式")
    return routes


def parse_routes_json(data: dict | list) -> List[Route]:
    """
    JSON 示例:
    {
      "routes": [
        {
          "name": "Route A",
          "sequence": ["CCO", "CC=O", "CC(=O)O"],
          "note": "oxidation"
        },
        {
          "name": "Route B",
          "reactions": ["CCO.CC(=O)O>>CCOC(=O)C", "CCOC(=O)C>>CC(=O)O"]
        }
      ]
    }
    """
    if isinstance(data, list):
        items = data
    else:
        items = data.get("routes") or data.get("pathways") or []

    routes: List[Route] = []
    for i, item in enumerate(items):
        name = item.get("name") or f"Route {i + 1}"
        note = item.get("note") or ""
        if "sequence" in item:
            seq = " -> ".join(item["sequence"])
            route = parse_molecule_sequence(seq, route_name=name)
            route.note = note
            routes.append(route)
        elif "reactions" in item:
            steps = [
                parse_step(rxn, label=f"Step {j + 1}")
                for j, rxn in enumerate(item["reactions"])
            ]
            routes.append(Route(name=name, steps=steps, note=note))
        elif "steps" in item:
            steps = [
                parse_step(s if isinstance(s, str) else s.get("smiles", ""), label=f"Step {j+1}")
                for j, s in enumerate(item["steps"])
            ]
            routes.append(Route(name=name, steps=steps, note=note))
        else:
            raise ValueError(f"路由缺少 sequence/reactions/steps: {item}")
    return routes


def _font(size: int = 16) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "segoeui.ttf", "msyh.ttc", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _render_mol(mol: Chem.Mol, size: Tuple[int, int]) -> Image.Image:
    return Draw.MolToImage(mol, size=size)


def _render_reaction(rxn: AllChem.ChemicalReaction, size: Tuple[int, int]) -> Image.Image:
    # subImgSize 控制每个组分大小；整体宽度由反应物/产物数量决定
    w, h = size
    n = max(rxn.GetNumReactantTemplates() + rxn.GetNumProductTemplates(), 1)
    sub_w = max(140, w // max(n, 2))
    return Draw.ReactionToImage(rxn, subImgSize=(sub_w, h))


def _text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _draw_arrow(draw: ImageDraw.ImageDraw, x0: int, y: int, x1: int, color=(40, 40, 40)) -> None:
    draw.line((x0, y, x1, y), fill=color, width=3)
    # 箭头头部
    draw.polygon([(x1, y), (x1 - 10, y - 6), (x1 - 10, y + 6)], fill=color)


def render_route(
    route: Route,
    mol_size: Tuple[int, int] = (220, 160),
    title_font_size: int = 20,
    label_font_size: int = 14,
) -> Image.Image:
    title_font = _font(title_font_size)
    label_font = _font(label_font_size)
    note_font = _font(12)

    # 先渲染每个 step 的图
    panels: List[Tuple[Image.Image, str]] = []
    for step in route.steps:
        if step.reaction is not None:
            img = _render_reaction(step.reaction, mol_size)
        elif len(step.molecules) == 1:
            img = _render_mol(step.molecules[0], mol_size)
        else:
            # 多分子并排
            parts = [_render_mol(m, mol_size) for m in step.molecules]
            w = sum(p.width for p in parts) + 8 * (len(parts) - 1)
            h = max(p.height for p in parts)
            canvas = Image.new("RGB", (w, h), "white")
            x = 0
            for p in parts:
                canvas.paste(p, (x, (h - p.height) // 2))
                x += p.width + 8
            img = canvas
        panels.append((img, step.label))

    # 测算标题
    probe = Image.new("RGB", (10, 10), "white")
    probe_draw = ImageDraw.Draw(probe)
    title = route.name
    if route.note:
        title = f"{route.name}  |  {route.note}"
    tw, th = _text_size(probe_draw, title, title_font)

    arrow_w = 36
    content_w = sum(p.width for p, _ in panels) + arrow_w * max(len(panels) - 1, 0)
    label_h = 22
    width = max(content_w, tw) + PAD * 2
    height = PAD + th + 12 + mol_size[1] + label_h + PAD

    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((PAD, PAD), title, fill=(20, 20, 20), font=title_font)

    y0 = PAD + th + 12
    x = PAD + max(0, (width - content_w - PAD * 2) // 2)

    for i, (img, label) in enumerate(panels):
        canvas.paste(img, (x, y0))
        lw, _ = _text_size(draw, label, label_font)
        draw.text(
            (x + (img.width - lw) // 2, y0 + img.height + 2),
            label,
            fill=(60, 60, 60),
            font=label_font,
        )
        if i < len(panels) - 1:
            ax0 = x + img.width + 4
            ax1 = ax0 + arrow_w - 8
            _draw_arrow(draw, ax0, y0 + img.height // 2, ax1)
            x = ax0 + arrow_w
        else:
            x += img.width

    # 轻微边框
    draw.rectangle([0, 0, width - 1, height - 1], outline=(220, 220, 220), width=1)
    return canvas


def render_comparison(
    routes: Sequence[Route],
    mol_size: Tuple[int, int] = (220, 160),
    header: str = "Synthetic Pathway Comparison",
) -> Image.Image:
    if not routes:
        raise ValueError("没有可绘制的路径")

    route_imgs = [render_route(r, mol_size=mol_size) for r in routes]
    header_font = _font(22)
    probe = Image.new("RGB", (10, 10), "white")
    pd = ImageDraw.Draw(probe)
    hw, hh = _text_size(pd, header, header_font)

    width = max(max(im.width for im in route_imgs), hw + PAD * 2) + PAD
    height = PAD + hh + 16 + sum(im.height for im in route_imgs) + ROUTE_GAP * (
        len(route_imgs) - 1
    ) + PAD

    canvas = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(canvas)
    draw.text((PAD, PAD), header, fill=(10, 10, 10), font=header_font)

    y = PAD + hh + 16
    for im in route_imgs:
        x = PAD + max(0, (width - im.width - PAD * 2) // 2)
        canvas.paste(im, (x, y))
        y += im.height + ROUTE_GAP

    draw.rectangle([0, 0, width - 1, height - 1], outline=(180, 180, 180), width=2)
    return canvas


def load_input(
    text: Optional[str] = None,
    file: Optional[Path] = None,
) -> List[Route]:
    if file is not None:
        raw = file.read_text(encoding="utf-8")
        if file.suffix.lower() == ".json":
            return parse_routes_json(json.loads(raw))
        return parse_routes_text(raw)
    if text:
        text = text.strip()
        if text.startswith("{") or text.startswith("["):
            return parse_routes_json(json.loads(text))
        return parse_routes_text(text)
    raise ValueError("请提供 --file 或命令行路径文本")


DEMO_TEXT = """# Route A | oxidation
CCO -> CC=O -> CC(=O)O

# Route B | via ester
CCO -> CCOC(=O)C -> CC(=O)O
"""


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="多步 SMILES → 反应路径对比图 PNG（无需分子通用名）"
    )
    parser.add_argument(
        "pathway",
        nargs="?",
        help='路径文本，例如: "CCO -> CC=O -> CC(=O)O"',
    )
    parser.add_argument("-f", "--file", type=Path, help="输入 .txt / .json")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("outputs/pathway.png"),
        help="输出 PNG 路径",
    )
    parser.add_argument(
        "--size",
        type=int,
        nargs=2,
        metavar=("W", "H"),
        default=(220, 160),
        help="每个结构图尺寸，默认 220 160",
    )
    parser.add_argument(
        "--title",
        default="Synthetic Pathway Comparison",
        help="总标题",
    )
    parser.add_argument("--demo", action="store_true", help="运行内置双路径示例")
    args = parser.parse_args(argv)

    try:
        if args.demo:
            routes = parse_routes_text(DEMO_TEXT)
        else:
            routes = load_input(text=args.pathway, file=args.file)
        img = render_comparison(
            routes,
            mol_size=(args.size[0], args.size[1]),
            header=args.title,
        )
    except Exception as exc:  # noqa: BLE001 - CLI 友好报错
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    img.save(args.output)
    print(f"已保存: {args.output.resolve()}")
    print(f"路径数: {len(routes)}；总尺寸: {img.size[0]}x{img.size[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
